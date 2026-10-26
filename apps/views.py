from decimal import Decimal, InvalidOperation
import secrets
from datetime import date
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import login, logout
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import LoginView, PasswordChangeView
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.core.exceptions import PermissionDenied
from django.db.models.deletion import ProtectedError
from django.db import IntegrityError, transaction
from django.db.models import Avg, Count, F, IntegerField, Max, OuterRef, Prefetch, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.db.models.functions import TruncMonth
from django.utils import timezone
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.text import slugify
from django.views.decorators.http import require_http_methods, require_POST
from django.views.generic import FormView, TemplateView
from django.views.generic.base import View

from .forms import (
    AddressForm,
    CheckoutForm,
    ContactForm,
    EmailAuthenticationForm,
    ProductCreateForm,
    ProductUpdateForm,
    ProductVariantForm,
    ProfileForm,
    ReturnRequestForm,
    ReviewForm,
    SellerApplicationForm,
    SellerProfileForm,
    SuperAdminShopCreateForm,
    SuperAdminShopEditForm,
    UserRegistrationForm,
)
from .models import (
    Brand,
    Category,
    Address,
    Chat,
    ChatMessage,
    ContactMessage,
    DeliveryPoint,
    Notification,
    Order,
    OrderItem,
    Product,
    ProductVariant,
    Review,
    ReturnRequest,
    Seller,
    SellerApplication,
    SellerOrder,
    Store,
    User,
    Wishlist,
)
from .services import (
    AddressService,
    CartError,
    CartService,
    ChatService,
    CheckoutError,
    CheckoutService,
    NotificationService,
    OrderActionError,
    OrderService,
    SellerOrderService,
    delete_store_preserving_history,
)
from .store_emails import store_email_for_seller


def card_products(in_stock=True):
    products = Product.objects.filter(
        is_active=True,
        seller__is_active=True,
    ).filter(Q(store__isnull=True) | Q(store__is_active=True)).distinct()
    if in_stock:
        products = products.filter(stock__gt=0)
    return (
        products
        .select_related("brand", "category", "category__store", "store", "seller")
        .annotate(
            average_rating=Coalesce(Avg("reviews__rating"), Value(0.0)),
            review_count=Count("reviews", distinct=True),
        )
    )


def active_seller_for_user(user):
    seller = Seller.objects.filter(user=user, is_active=True).first()
    return seller if seller and seller.shop_is_active else None


def with_sales_count(queryset):
    excluded_statuses = (Order.Status.CANCELLED, Order.Status.RETURNED)
    sales = (
        OrderItem.objects.filter(product=OuterRef("pk"))
        .exclude(order__status__in=excluded_statuses)
        .values("product")
        .annotate(total=Sum("quantity"))
        .values("total")
    )
    return queryset.annotate(
        sales_count=Coalesce(
            Subquery(sales, output_field=IntegerField()),
            Value(0),
        )
    )


def category_descendant_ids(category):
    """Return the category and all of its descendants without assuming a fixed depth."""
    category_ids = [category.pk]
    pending_ids = [category.pk]
    while pending_ids:
        pending_ids = list(
            Category.objects.filter(parent_id__in=pending_ids, is_active=True)
            .values_list("pk", flat=True)
        )
        category_ids.extend(pending_ids)
    return category_ids


def category_breadcrumbs(category):
    breadcrumbs = []
    current = category
    while current is not None:
        breadcrumbs.append(current)
        current = current.parent
    return list(reversed(breadcrumbs))


def decimal_query_value(params, name):
    value = params.get(name, "").strip()
    if not value:
        return None
    try:
        number = Decimal(value)
    except InvalidOperation:
        return None
    return number if number >= 0 else None


def filter_and_sort_products(queryset, params):
    brand_slug = params.get("brand", "").strip()
    min_price = decimal_query_value(params, "min_price")
    max_price = decimal_query_value(params, "max_price")
    discount_only = params.get("discount") == "1"
    availability = params.get("availability", "in_stock")
    if availability not in {"in_stock", "out_of_stock", "all"}:
        availability = "in_stock"

    try:
        minimum_rating = int(params.get("rating", "") or 0)
    except ValueError:
        minimum_rating = 0
    if minimum_rating not in range(1, 6):
        minimum_rating = 0

    if brand_slug:
        queryset = queryset.filter(brand__slug=brand_slug)
    if min_price is not None:
        queryset = queryset.filter(price__gte=min_price)
    if max_price is not None:
        queryset = queryset.filter(price__lte=max_price)
    if discount_only:
        queryset = queryset.filter(old_price__isnull=False, old_price__gt=F("price"))
    if minimum_rating:
        queryset = queryset.filter(average_rating__gte=minimum_rating)
    if availability == "in_stock":
        queryset = queryset.filter(stock__gt=0)
    elif availability == "out_of_stock":
        queryset = queryset.filter(stock=0)

    queryset = with_sales_count(queryset)
    sort = params.get("sort", "popular")
    ordering = {
        "popular": ("-sales_count", "-created_at"),
        "price_asc": ("price", "name"),
        "price_desc": ("-price", "name"),
        "rating": ("-average_rating", "-review_count", "name"),
        "newest": ("-created_at",),
    }
    if sort not in ordering:
        sort = "popular"

    state = {
        "brand": brand_slug,
        "min_price": params.get("min_price", "").strip(),
        "max_price": params.get("max_price", "").strip(),
        "discount": discount_only,
        "rating": minimum_rating,
        "availability": availability,
        "sort": sort,
    }
    return queryset.order_by(*ordering[sort]), state


def paginated_product_context(request, queryset, per_page=12):
    paginator = Paginator(queryset, per_page)
    page_obj = paginator.get_page(request.GET.get("page"))
    query_params = request.GET.copy()
    query_params.pop("page", None)
    return {
        "products": page_obj.object_list,
        "page_obj": page_obj,
        "paginator": paginator,
        "is_paginated": page_obj.has_other_pages(),
        "filter_query": query_params.urlencode(),
        "product_count": paginator.count,
    }


class CategoryView(TemplateView):
    template_name = "category.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        category = get_object_or_404(
            Category.objects.select_related("parent"),
            slug=self.kwargs["slug"],
            is_active=True,
        )
        category_ids = category_descendant_ids(category)
        base_products = card_products(in_stock=False).filter(category_id__in=category_ids)
        brands = Brand.objects.filter(
            is_active=True,
            products__in=base_products,
        ).distinct().order_by("name")
        products, filter_state = filter_and_sort_products(base_products, self.request.GET)
        children = list(
            category.children.filter(is_active=True)
            .annotate(
                product_count=Count(
                    "products",
                    filter=Q(
                        products__is_active=True,
                        products__stock__gt=0,
                        products__seller__is_active=True,
                    ) & (
                        Q(products__store__isnull=True)
                        | Q(products__store__is_active=True)
                    ),
                    distinct=True,
                )
            )
            .order_by("name")
        )

        context.update(paginated_product_context(self.request, products))
        context.update({
                "page_title": f"{category.name} — Zento",
                "category": category,
                "parent_category": category.parent,
                "child_categories": children,
                "breadcrumbs": category_breadcrumbs(category),
                "brands": brands,
                "filter_state": filter_state,
                "reset_url": self.request.path,
            })
        return context


class ProductDetailView(TemplateView):
    template_name = "product.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product = get_object_or_404(
            Product.objects.filter(
                is_active=True,
                seller__is_active=True,
            ).filter(Q(store__isnull=True) | Q(store__is_active=True))
            .select_related("brand", "category", "category__parent", "category__store", "store", "seller")
            .prefetch_related(
                Prefetch(
                    "variants",
                    queryset=ProductVariant.objects.filter(is_active=True).order_by("id"),
                    to_attr="active_variants",
                ),
                Prefetch(
                    "reviews",
                    queryset=Review.objects.select_related("user").order_by("-created_at"),
                    to_attr="product_reviews",
                ),
            )
            .annotate(
                average_rating=Coalesce(Avg("reviews__rating"), Value(0.0)),
                review_count=Count("reviews", distinct=True),
            ),
            slug=self.kwargs["slug"],
        )
        sales_count = (
            product.order_items.exclude(
                order__status__in=(Order.Status.CANCELLED, Order.Status.RETURNED)
            ).aggregate(total=Coalesce(Sum("quantity"), Value(0)))["total"]
        )
        variants = product.active_variants
        selected_variant = (
            next((variant for variant in variants if variant.stock), variants[0])
            if variants
            else None
        )
        display_price = selected_variant.final_price if selected_variant else product.price
        display_stock = selected_variant.stock if selected_variant else product.stock
        related_products = with_sales_count(card_products().filter(
            category=product.category
        ).exclude(pk=product.pk)).order_by("-sales_count", "-average_rating", "-created_at")[:5]

        context.update(
            {
                "page_title": f"{product.name} — Zento",
                "product": product,
                "breadcrumbs": category_breadcrumbs(product.category),
                "variants": variants,
                "selected_variant": selected_variant,
                "display_price": display_price,
                "display_installment_price": display_price / 12,
                "display_stock": display_stock,
                "reviews": product.product_reviews,
                "sales_count": sales_count,
                "related_products": related_products,
                "is_out_of_stock": display_stock <= 0,
            }
        )
        return context


class SellerDetailView(TemplateView):
    template_name = "seller.html"

    def get_seller(self):
        raw_value = (
            self.kwargs.get("pk_or_slug")
            or self.kwargs.get("slug")
            or self.kwargs.get("pk")
        )
        if raw_value is None:
            raise Http404("Seller not found.")

        value = str(raw_value).strip()
        queryset = Seller.objects.filter(is_active=True)
        if value.isdigit():
            return get_object_or_404(queryset, pk=value)

        target_slug = slugify(value)
        seller = queryset.filter(store_name__iexact=value).first()
        if seller is None:
            seller = queryset.filter(store_name__icontains=value).first()
        if seller is None:
            for candidate in queryset.all():
                if slugify(candidate.store_name) == target_slug:
                    seller = candidate
                    break
        if seller is None:
            raise Http404("Seller not found.")
        return seller

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        seller = self.get_seller()
        base_products = card_products(in_stock=False).filter(seller=seller)
        brands = Brand.objects.filter(is_active=True, products__in=base_products).distinct().order_by("name")
        products, filter_state = filter_and_sort_products(base_products, self.request.GET)
        seller_stats = seller.products.filter(is_active=True).aggregate(
            average_product_rating=Coalesce(Avg("reviews__rating"), Value(0.0)),
            review_count=Count("reviews", distinct=True),
            total_stock=Coalesce(Sum("stock"), Value(0)),
        )
        sales_count = (
            OrderItem.objects.filter(seller=seller)
            .exclude(order__status__in=(Order.Status.CANCELLED, Order.Status.RETURNED))
            .aggregate(total=Coalesce(Sum("quantity"), Value(0)))["total"]
        )
        context.update(
            {
                "page_title": f"{seller.store_name} — Zento",
                "seller": seller,
                "seller_rating": seller_stats["average_product_rating"],
                "average_product_rating": seller_stats["average_product_rating"],
                "review_count": seller_stats["review_count"],
                "total_stock": seller_stats["total_stock"],
                "sales_count": sales_count,
                "brands": brands,
                "filter_state": filter_state,
                "reset_url": self.request.path,
            }
        )
        context.update(paginated_product_context(self.request, products))
        context["product_count"] = context["paginator"].count
        return context


def legacy_category_redirect(request):
    category = Category.objects.filter(is_active=True).order_by("name").first()
    return redirect("apps:category", slug=category.slug) if category else redirect("apps:catalog")


def legacy_product_redirect(request):
    product = Product.objects.filter(
        is_active=True,
        seller__is_active=True,
    ).order_by("-created_at").first()
    return redirect("apps:product", slug=product.slug) if product else redirect("apps:catalog")


def legacy_seller_redirect(request):
    seller = Seller.objects.filter(is_active=True).order_by("store_name").first()
    if not seller:
        return redirect("apps:catalog")
    return redirect("apps:seller", pk=seller.pk)


class IndexView(TemplateView):
    template_name = "index.html"
    extra_context = {"page_title": "Zento — hammasi bir joyda"}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        products = card_products()
        valid_orders = ~Q(
            products__order_items__order__status__in=(
                Order.Status.CANCELLED,
                Order.Status.RETURNED,
            )
        )

        context["catalog_categories"] = (
            Category.objects.filter(is_active=True)
            .annotate(
                product_count=Count(
                    "products",
                    filter=Q(products__is_active=True),
                    distinct=True,
                )
            )
            .filter(product_count__gt=0)
            .order_by("name")[:12]
        )
        context["discount_products"] = products.filter(
            old_price__isnull=False,
            old_price__gt=F("price"),
        ).order_by("-created_at")[:5]
        context["best_sellers"] = with_sales_count(products).order_by(
            "-sales_count", "-created_at"
        )[:5]
        context["popular_brands"] = (
            Brand.objects.filter(is_active=True, products__is_active=True)
            .annotate(
                sales_count=Coalesce(
                    Sum("products__order_items__quantity", filter=valid_orders),
                    Value(0),
                    output_field=IntegerField(),
                ),
                product_count=Count(
                    "products",
                    filter=Q(products__is_active=True),
                    distinct=True,
                ),
            )
            .order_by("-sales_count", "-product_count", "name")[:8]
        )
        return context


class CatalogView(TemplateView):
    template_name = "catalog.html"
    extra_context = {"page_title": "Katalog — Zento"}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["categories"] = (
            Category.objects.filter(is_active=True)
            .annotate(
                product_count=Count(
                    "products",
                    filter=Q(products__is_active=True),
                    distinct=True,
                )
            )
            .order_by("name")
        )
        return context


class CategoriesListView(TemplateView):
    template_name = "categories.html"
    extra_context = {"page_title": "Kategoriyalar — Zento"}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["categories"] = Category.objects.filter(is_active=True).annotate(
            product_count=Count(
                "products",
                filter=Q(
                    products__is_active=True,
                    products__seller__is_active=True,
                ) & (
                    Q(products__store__isnull=True)
                    | Q(products__store__is_active=True)
                ),
                distinct=True,
            )
        )
        return context


class StoreListView(TemplateView):
    template_name = "stores.html"
    extra_context = {"page_title": "Do‘konlar — Zento"}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["stores"] = Store.objects.annotate(
            product_count=Count(
                "products",
                filter=Q(
                    products__is_active=True,
                    products__seller__is_active=True,
                ) & (
                    Q(products__store__isnull=True)
                    | Q(products__store__is_active=True)
                ),
                distinct=True,
            )
        ).filter(Q(seller__isnull=True) | Q(is_active=True))
        return context


class StoreDetailView(TemplateView):
    template_name = "store.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        store = get_object_or_404(Store, slug=self.kwargs["slug"])
        if store.seller_id and not store.is_active:
            raise Http404
        products = (
            Product.objects.filter(
                store=store,
                is_active=True,
                seller__is_active=True,
            )
            .select_related("category", "store")
        )
        context.update({"store": store, "products": products, "page_title": f"{store.name} — Zento"})
        return context


class ProductListView(TemplateView):
    template_name = "products.html"
    extra_context = {"page_title": "Barcha mahsulotlar — Zento"}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["products"] = card_products(in_stock=False)
        return context


class ProductIdDetailView(TemplateView):
    template_name = "product-universal.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product = get_object_or_404(
            Product.objects.filter(
                is_active=True,
                seller__is_active=True,
            )
            .select_related("category", "store"),
            pk=self.kwargs["product_id"],
        )
        context.update({"product": product, "page_title": f"{product.name} — Zento"})
        return context


class CartView(LoginRequiredMixin, TemplateView):
    template_name = "cart.html"
    extra_context = {"page_title": "Savat — Zento"}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cart = CartService.get_cart(self.request.user)
        items, count, total = CartService.summary(cart)
        for item in items:
            item.current_price = item.variant.final_price if item.variant else item.product.price
            item.price_changed = item.current_price != item.price
            item.subtotal = item.price * item.quantity
        context.update({
            "cart": cart,
            "cart_items": items,
            "cart_count": count,
            "cart_total": total,
        })
        return context


def _cart_response(request, callback):
    if not request.user.is_authenticated:
        next_url = request.META.get("HTTP_REFERER") or reverse_lazy("apps:cart")
        return JsonResponse({
            "success": False,
            "error": "Kirish talab qilinadi.",
            "login_url": f"{reverse_lazy('apps:login')}?{urlencode({'next': next_url})}",
        }, status=401)
    try:
        result = callback()
    except CartError as exc:
        return JsonResponse({"success": False, "error": str(exc)}, status=400)
    cart = CartService.get_cart(request.user)
    _, count, total = CartService.summary(cart)
    data = {"success": True, "cart_count": count, "cart_total": str(total)}
    if result is not None:
        data["item_id"] = result.pk
        data["quantity"] = result.quantity
    return JsonResponse(data)


@require_http_methods(["POST"])
def cart_add(request):
    return _cart_response(request, lambda: CartService.add(
        request.user,
        request.POST.get("product_id"),
        request.POST.get("variant_id") or None,
        request.POST.get("quantity", 1),
    ))


@require_http_methods(["POST"])
def cart_update(request, item_id):
    return _cart_response(request, lambda: CartService.set_quantity(
        request.user, item_id, request.POST.get("quantity")
    ))


@require_http_methods(["POST"])
def cart_remove(request, item_id):
    return _cart_response(request, lambda: (CartService.remove(request.user, item_id) or None))


@require_http_methods(["POST"])
def cart_clear(request):
    return _cart_response(request, lambda: (CartService.clear(request.user) or None))


class SearchView(TemplateView):
    template_name = "search.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        query = self.request.GET.get("q", "").strip()
        category_slug = self.request.GET.get("category", "").strip()

        products = card_products(in_stock=False)
        if query:
            products = products.filter(
                Q(name__icontains=query)
                | Q(description__icontains=query)
                | Q(sku__icontains=query)
                | Q(brand__name__icontains=query)
                | Q(category__name__icontains=query)
                | Q(seller__store_name__icontains=query)
            )
        if category_slug:
            category = Category.objects.filter(slug=category_slug, is_active=True).first()
            products = products.filter(
                category_id__in=category_descendant_ids(category)
            ) if category else products.none()

        brands = Brand.objects.filter(
            is_active=True,
            products__in=products,
        ).distinct().order_by("name")
        products, filter_state = filter_and_sort_products(products, self.request.GET)

        title = f"“{query}” bo‘yicha natijalar" if query else "Mahsulotlar"
        if category_slug and not query:
            category = Category.objects.filter(slug=category_slug).first()
            title = category.name if category else title
        if filter_state["brand"] and not query:
            brand = Brand.objects.filter(slug=filter_state["brand"]).first()
            title = brand.name if brand else title
        if filter_state["discount"] and not query:
            title = "Chegirmali mahsulotlar"

        reset_params = self.request.GET.copy()
        for name in ("brand", "min_price", "max_price", "discount", "rating", "availability", "sort", "page"):
            reset_params.pop(name, None)
        reset_query = reset_params.urlencode()

        context.update(paginated_product_context(self.request, products))
        context.update({
                "page_title": f"{title} — Zento",
                "search_title": title,
                "query": query,
                "result_count": context["product_count"],
                "brands": brands,
                "filter_state": filter_state,
                "reset_url": f"{self.request.path}?{reset_query}" if reset_query else self.request.path,
            })
        return context


class LoginPageView(LoginView):
    template_name = "login.html"
    authentication_form = EmailAuthenticationForm
    next_page = reverse_lazy("apps:index")
    extra_context = {"page_title": "Kirish — Zento", "compact_layout": True}

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("apps:index")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        if not form.cleaned_data.get("remember_me"):
            self.request.session.set_expiry(0)
        return response

    def get_success_url(self):
        url = super().get_success_url()
        if self.request.GET.get("next") or self.request.POST.get("next"):
            return url
        if active_seller_for_user(self.request.user):
            return reverse_lazy("apps:seller-dashboard")
        return url


class LogoutPageView(View):
    def post(self, request):
        user = self.request.user
        if user.is_authenticated:
            logout(self.request)
            return redirect("apps:index")


class RegisterPageView(FormView):
    template_name = "signup.html"
    form_class = UserRegistrationForm
    success_url = reverse_lazy("apps:index")
    extra_context = {"page_title": "Ro‘yxatdan o‘tish — Zento", "compact_layout": True}

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("apps:index")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        user = form.save()
        login(self.request, user, backend="django.contrib.auth.backends.ModelBackend")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["next"] = self.request.POST.get("next") or self.request.GET.get("next")
        return context

    def get_success_url(self):
        next_url = self.request.POST.get("next") or self.request.GET.get("next")
        if next_url and url_has_allowed_host_and_scheme(
                next_url,
                allowed_hosts={self.request.get_host()},
                require_https=self.request.is_secure(),
        ):
            return next_url
        return str(self.success_url)


class SellerRequiredMixin(LoginRequiredMixin):
    """Require an active shop profile linked to the authenticated account."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        self.seller = active_seller_for_user(request.user)
        if self.seller is None or not (
            request.user.is_superuser or request.user.has_perm("apps.manage_shop_dashboard")
        ):
            raise PermissionDenied("Faqat faol sotuvchilar ushbu sahifadan foydalana oladi.")
        return super().dispatch(request, *args, **kwargs)


def get_shop_admin_seller(request):
    seller = active_seller_for_user(request.user)
    if seller is None or not (
        request.user.is_superuser or request.user.has_perm("apps.manage_shop_dashboard")
    ):
        raise PermissionDenied("Faol shop admin hisobi talab qilinadi.")
    return seller


class SellerApplicationView(LoginRequiredMixin, FormView):
    template_name = "sell.html"
    form_class = SellerApplicationForm
    success_url = reverse_lazy("apps:sell")
    extra_context = {"page_title": "Zento'da soting"}

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and active_seller_for_user(request.user):
            return redirect("apps:seller-dashboard")
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        initial = super().get_initial()
        initial.update({
            "full_name": self.request.user.get_full_name(),
            "phone": self.request.user.phone,
        })
        return initial

    def form_valid(self, form):
        try:
            # A savepoint keeps the request transaction usable when the partial
            # unique constraint rejects a double submit.
            with transaction.atomic():
                application = form.save(commit=False)
                application.user = self.request.user
                application.save()
        except IntegrityError:
            form.add_error(None, "Sizda ko‘rib chiqilayotgan sotuvchi arizasi bor.")
            return self.form_invalid(form)
        messages.success(self.request, "Arizangiz yuborildi. Natija xabarnomalarda chiqadi.")
        return super().form_valid(form)


class SellerDashboardView(SellerRequiredMixin, TemplateView):
    template_name = "seller-dashboard.html"
    extra_context = {"page_title": "Do‘kon boshqaruvi — Zento", "active_page": "seller-dashboard"}

    def get_form(self):
        return SellerProfileForm(
            self.request.POST or None,
            self.request.FILES or None,
            instance=self.seller,
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        products = self.seller.products.all()
        today = timezone.localdate()
        month_start = today.replace(day=1)
        today_sales = seller_sales(self.seller, today=today)
        monthly_sales = seller_sales(self.seller, date_from=month_start)
        context.update({
            "seller": self.seller,
            "form": kwargs.get("form", self.get_form()),
            "product_count": products.count(),
            "active_product_count": products.filter(is_active=True, stock__gt=0).count(),
            "inactive_product_count": products.filter(is_active=False).count(),
            "out_of_stock_product_count": products.filter(is_active=True, stock=0).count(),
            "order_count": SellerOrder.objects.filter(seller=self.seller).count(),
            "new_order_count": SellerOrder.objects.filter(seller=self.seller, status=Order.Status.NEW).count(),
            "shipping_order_count": SellerOrder.objects.filter(seller=self.seller, status=Order.Status.SHIPPED).count(),
            "pickup_order_count": SellerOrder.objects.filter(
                seller=self.seller,
                status=Order.Status.READY_FOR_PICKUP,
            ).count(),
            "delivered_order_count": SellerOrder.objects.filter(
                seller=self.seller,
                status=Order.Status.DELIVERED,
            ).count(),
            "today_sales": today_sales,
            "monthly_sales": monthly_sales,
            "customer_count": SellerOrder.objects.filter(seller=self.seller)
                .values("order__user_id").distinct().count(),
        })
        return context

    def post(self, request, *args, **kwargs):
        form = self.get_form()
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))
        form.save()
        messages.success(request, "Do‘kon profili saqlandi.")
        return redirect("apps:seller-dashboard")


def seller_sales(seller, *, today=None, date_from=None):
    shop_orders = SellerOrder.objects.filter(seller=seller).exclude(
        status__in=(Order.Status.CANCELLED, Order.Status.RETURNED)
    )
    if today:
        shop_orders = shop_orders.filter(order__created_at__date=today)
    if date_from:
        shop_orders = shop_orders.filter(order__created_at__date__gte=date_from)
    return OrderItem.objects.filter(
        seller=seller,
        order_id__in=shop_orders.values("order_id"),
    ).aggregate(
        total=Sum(F("price") * F("quantity"))
    )["total"] or Decimal("0")


class SuperAdminRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_superuser


class SuperAdminDashboardView(SuperAdminRequiredMixin, TemplateView):
    template_name = "super-admin-dashboard.html"
    extra_context = {"page_title": "Super Admin — Zento"}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        all_shops = Store.objects.filter(seller__isnull=False).select_related(
            "seller", "seller__user"
        ).order_by("name")
        shops = all_shops
        query = self.request.GET.get("q", "").strip()
        status = self.request.GET.get("status", "")
        if query:
            shops = shops.filter(
                Q(name__icontains=query)
                | Q(shop_code__icontains=query)
                | Q(seller__user__email__icontains=query)
            )
        if status == "active":
            shops = shops.filter(is_active=True, seller__user__is_active=True)
        elif status == "inactive":
            shops = shops.filter(Q(is_active=False) | Q(seller__user__is_active=False))

        today = timezone.localdate()
        first_chart_month = date(today.year, today.month, 1)
        for _ in range(5):
            first_chart_month = date(
                first_chart_month.year - (first_chart_month.month == 1),
                (first_chart_month.month - 2) % 12 + 1,
                1,
            )
        monthly_data = {
            row["month"].date().replace(day=1): row
            for row in Order.objects.filter(
                created_at__date__gte=first_chart_month,
                created_at__date__lte=today,
            ).annotate(month=TruncMonth("created_at"))
            .values("month")
            .annotate(order_count=Count("pk"), revenue=Sum("total"))
        }
        sales_chart = []
        current_month = first_chart_month
        for _ in range(6):
            row = monthly_data.get(current_month, {})
            sales_chart.append({
                "label": f"{current_month.month:02d}/{current_month.year}",
                "order_count": row.get("order_count", 0),
                "revenue": row.get("revenue") or Decimal("0"),
            })
            next_month = current_month.month % 12 + 1
            current_month = date(current_month.year + (current_month.month == 12), next_month, 1)
        max_orders = max((item["order_count"] for item in sales_chart), default=0)
        for item in sales_chart:
            item["bar_width"] = round(item["order_count"] / max_orders * 100) if max_orders else 0

        context.update({
            "shops": shops,
            "shop_count": all_shops.count(),
            "product_count": Product.objects.count(),
            "order_count": Order.objects.count(),
            "user_count": User.objects.count(),
            "active_shop_count": all_shops.filter(is_active=True, seller__user__is_active=True).count(),
            "query": query,
            "selected_status": status,
            "sales_chart": sales_chart,
        })
        return context


class SuperAdminShopCreateView(SuperAdminRequiredMixin, FormView):
    template_name = "super-admin-shop-form.html"
    form_class = SuperAdminShopCreateForm
    extra_context = {"page_title": "Shop yaratish — Super Admin"}

    def form_valid(self, form):
        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    email=form.cleaned_data["email"],
                    password=form.cleaned_data["password"],
                    phone=form.cleaned_data["phone"],
                    role=User.Role.SELLER,
                )
                seller = Seller.objects.create(
                    user=user,
                    store_name=form.cleaned_data["store_name"],
                    description=form.cleaned_data["description"],
                    phone=form.cleaned_data["phone"],
                )
                shop = seller.shop_store
                shop.description = form.cleaned_data["description"]
                shop.email = store_email_for_seller(seller, shop)
                shop.save(update_fields=["description", "email", "updated_at"])
        except IntegrityError:
            form.add_error(None, "Shop nomi yoki admin emaili allaqachon ishlatilmoqda.")
            return self.form_invalid(form)
        messages.success(self.request, f"{shop.name} shopi yaratildi. Shop code: {shop.shop_code}")
        return redirect("apps:super-admin")


class SuperAdminShopEditView(SuperAdminRequiredMixin, FormView):
    template_name = "super-admin-shop-form.html"
    extra_context = {"page_title": "Shopni tahrirlash — Super Admin"}

    def get_shop(self):
        return get_object_or_404(
            Store.objects.select_related("seller", "seller__user"),
            pk=self.kwargs["shop_id"],
            seller__isnull=False,
        )

    def get_form_class(self):
        return SuperAdminShopEditForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["store"] = self.get_shop()
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({"shop": self.get_shop(), "is_edit": True})
        return context

    def form_valid(self, form):
        shop = self.get_shop()
        seller = shop.seller
        admin_user = seller.user
        data = form.cleaned_data
        try:
            with transaction.atomic():
                admin_user.email = data["admin_email"]
                admin_user.phone = data["phone"]
                admin_user.is_active = data["admin_is_active"]
                if data["new_password"]:
                    admin_user.set_password(data["new_password"])
                admin_user.save()

                seller.store_name = data["store_name"]
                seller.phone = data["phone"]
                seller.is_active = data["store_is_active"]
                seller.save()

                shop.name = data["store_name"]
                shop.description = data["description"]
                shop.email = store_email_for_seller(seller, shop)
                shop.is_active = data["store_is_active"]
                shop.save()
        except IntegrityError:
            form.add_error(None, "Shop nomi yoki admin emaili boshqa yozuvda ishlatilmoqda.")
            return self.form_invalid(form)
        messages.success(self.request, "Shop va shop admin ma’lumotlari saqlandi.")
        return redirect("apps:super-admin")


@login_required
@require_POST
def super_admin_toggle_shop(request, shop_id):
    if not request.user.is_superuser:
        raise PermissionDenied
    shop = get_object_or_404(Store.objects.select_related("seller", "seller__user"), pk=shop_id, seller__isnull=False)
    shop.is_active = not shop.is_active
    shop.seller.is_active = shop.is_active
    shop.save(update_fields=["is_active", "updated_at"])
    shop.seller.save(update_fields=["is_active", "updated_at"])
    messages.success(request, f"{shop.name}: {'faollashtirildi' if shop.is_active else 'faolsizlantirildi'}.")
    return redirect("apps:super-admin")


@login_required
@require_POST
def super_admin_delete_shop(request, shop_id):
    if not request.user.is_superuser:
        raise PermissionDenied
    shop = get_object_or_404(
        Store.objects.select_related("seller", "seller__user"),
        pk=shop_id,
        seller__isnull=False,
    )
    try:
        delete_store_preserving_history(shop)
    except ProtectedError:
        messages.error(
            request,
            "Shopni o‘chirib bo‘lmadi: buyurtma yoki boshqa himoyalangan tarixga bog‘langan ma’lumot mavjud.",
        )
    else:
        messages.success(
            request,
            "Shop o‘chirildi. Mahsulotlar va tarix saqlandi; asosiy shop bo‘lsa admin hisobi faolsizlantirildi.",
        )
    return redirect("apps:super-admin")


class SellerProductsView(SellerRequiredMixin, TemplateView):
    template_name = "seller-products.html"
    extra_context = {"page_title": "Mahsulotlarim — Zento", "active_page": "seller-products"}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        products = self.seller.products.select_related("category", "brand").prefetch_related("variants")
        query = self.request.GET.get("q", "").strip()
        if query:
            products = products.filter(Q(name__icontains=query) | Q(sku__icontains=query))
        paginator = Paginator(products, 15)
        page_obj = paginator.get_page(self.request.GET.get("page"))
        context.update({
            "products": page_obj,
            "query": query,
            "page_obj": page_obj,
        })
        return context


class AccountView(LoginRequiredMixin, TemplateView):
    template_name = "account.html"
    extra_context = {"page_title": "Shaxsiy kabinet — Zento", "active_page": "account"}

    def get_form(self):
        return ProfileForm(instance=self.request.user, data=self.request.POST or None, files=self.request.FILES or None)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        active_orders = self.request.user.orders.exclude(
            status__in=(Order.Status.CANCELLED, Order.Status.RETURNED)
        )
        context.update({
            "form": kwargs.get("form", self.get_form()),
            "active_order_count": active_orders.exclude(status=Order.Status.DELIVERED).count(),
            "wishlist_count": self.request.user.wishlist_items.count(),
            "order_count": self.request.user.orders.count(),
            "recent_order": active_orders.prefetch_related("items").first(),
        })
        return context

    def post(self, request, *args, **kwargs):
        form = self.get_form()
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))
        form.save()
        messages.success(request, "Profil ma’lumotlari saqlandi.")
        return redirect("apps:account")


class UserPasswordChangeView(LoginRequiredMixin, PasswordChangeView):
    template_name = "password_change.html"
    form_class = PasswordChangeForm
    success_url = reverse_lazy("apps:account")
    extra_context = {"page_title": "Parolni almashtirish — Zento", "compact_layout": True}

    def form_valid(self, form):
        response = super().form_valid(form)
        update_session_auth_hash(self.request, form.user)
        messages.success(self.request, "Parolingiz muvaffaqiyatli almashtirildi.")
        return response


class AddressView(LoginRequiredMixin, TemplateView):
    template_name = "addresses.html"
    extra_context = {"page_title": "Manzillarim — Zento", "active_page": "addresses"}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        edit_id = self.request.GET.get("edit")
        edit_address = (
            get_object_or_404(Address, pk=edit_id, user=self.request.user)
            if edit_id else None
        )
        context.update({
            "addresses": self.request.user.addresses.order_by("-is_default", "-updated_at"),
            "form": kwargs.get("form", AddressForm(instance=edit_address)),
            "editing_address": edit_address,
        })
        return context

    def post(self, request, *args, **kwargs):
        action = request.POST.get("action", "save")
        address_id = request.POST.get("address_id")
        if action == "delete":
            address = get_object_or_404(Address, pk=address_id, user=request.user)
            AddressService.delete(request.user, address.pk)
            messages.success(request, "Manzil o‘chirildi.")
            return redirect("apps:addresses")
        if action == "default":
            address = get_object_or_404(Address, pk=address_id, user=request.user)
            data = {
                field.name: getattr(address, field.name)
                for field in Address._meta.fields
                if field.name not in {"id", "user", "created_at", "updated_at"}
            }
            data["is_default"] = True
            AddressService.save(request.user, address, data)
            messages.success(request, "Asosiy manzil yangilandi.")
            return redirect("apps:addresses")

        address = (
            get_object_or_404(Address, pk=address_id, user=request.user)
            if address_id else Address(user=request.user)
        )
        form = AddressForm(request.POST, instance=address)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))
        AddressService.save(request.user, address, form.cleaned_data)
        messages.success(request, "Manzil saqlandi.")
        return redirect("apps:addresses")


class OrdersView(LoginRequiredMixin, TemplateView):
    template_name = "orders.html"
    extra_context = {"page_title": "Buyurtmalarim — Zento", "active_page": "orders"}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        orders = self.request.user.orders.prefetch_related(
            Prefetch(
                "items",
                queryset=OrderItem.objects.select_related("product", "variant", "seller"),
            )
        ).order_by("-created_at")
        status = self.request.GET.get("status", "").strip()
        if status in dict(Order.Status.choices):
            orders = orders.filter(status=status)
        else:
            status = ""
        date_from = self.request.GET.get("date_from", "").strip()
        date_to = self.request.GET.get("date_to", "").strip()
        try:
            if date_from:
                orders = orders.filter(created_at__date__gte=date.fromisoformat(date_from))
        except ValueError:
            date_from = ""
        try:
            if date_to:
                orders = orders.filter(created_at__date__lte=date.fromisoformat(date_to))
        except ValueError:
            date_to = ""
        paginator = Paginator(orders, 10)
        page_obj = paginator.get_page(self.request.GET.get("page"))
        context.update({
            "orders": page_obj,
            "page_obj": page_obj,
            "order_statuses": Order.Status.choices,
            "selected_status": status,
            "date_from": date_from,
            "date_to": date_to,
        })
        return context


class OrderDetailView(LoginRequiredMixin, TemplateView):
    template_name = "order-detail.html"
    extra_context = {"page_title": "Buyurtma tafsilotlari — Zento", "active_page": "orders"}

    def get_order(self):
        return get_object_or_404(
            Order.objects.select_related("address", "delivery_point", "payment").prefetch_related(
                Prefetch(
                    "items",
                    queryset=OrderItem.objects.select_related("product", "variant", "seller"),
                ),
                Prefetch(
                    "seller_orders",
                    queryset=SellerOrder.objects.select_related("seller").prefetch_related("status_history"),
                ),
            ),
            user=self.request.user,
            order_number=self.kwargs["order_number"],
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order = self.get_order()
        reviews = {
            review.product_id: review
            for review in Review.objects.filter(order=order, user=self.request.user)
        }
        status_values = list(Order.Status.values)
        current_index = status_values.index(order.status) if order.status in status_values else -1
        timeline = []
        for index, (value, label) in enumerate(Order.Status.choices):
            timeline.append({
                "value": value,
                "label": label,
                "completed": order.status != Order.Status.CANCELLED and index <= current_index,
                "current": value == order.status,
            })
        for item in order.items.all():
            item.user_review = reviews.get(item.product_id)
            if order.status == Order.Status.DELIVERED and not item.user_review:
                item.review_form = ReviewForm()
        context.update({
            "order": order,
            "order_items": order.items.all(),
            "seller_orders": order.seller_orders.all(),
            "status_timeline": timeline,
            "return_request": ReturnRequest.objects.filter(order=order).first(),
            "return_form": ReturnRequestForm(),
        })
        return context


@login_required
@require_POST
def cancel_order(request, order_number):
    get_object_or_404(Order, user=request.user, order_number=order_number)
    try:
        OrderService.cancel(request.user, order_number)
    except OrderActionError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Buyurtma bekor qilindi.")
    return redirect("apps:order-detail", order_number=order_number)


@login_required
@require_POST
def reorder(request, order_number):
    get_object_or_404(Order, user=request.user, order_number=order_number)
    try:
        added, skipped = OrderService.reorder(request.user, order_number)
    except (Order.DoesNotExist, Product.DoesNotExist):
        messages.error(request, "Buyurtma yoki mahsulot endi mavjud emas.")
    else:
        if added:
            messages.success(request, f"{len(added)} ta mahsulot savatga qo‘shildi.")
        if skipped:
            messages.warning(request, f"{len(skipped)} ta mahsulot qoldiq sababli qo‘shilmadi.")
        if not added:
            messages.error(request, "Qayta xarid qilish uchun mavjud mahsulot topilmadi.")
    return redirect("apps:cart")


@login_required
@require_POST
def create_review(request, order_number, item_id):
    order = get_object_or_404(Order, user=request.user, order_number=order_number)
    item = get_object_or_404(OrderItem, order=order, pk=item_id)
    if order.status != Order.Status.DELIVERED:
        messages.error(request, "Sharh faqat yetkazilgan buyurtma uchun yoziladi.")
        return redirect("apps:order-detail", order_number=order_number)
    form = ReviewForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Sharh ma’lumotlarini to‘g‘ri kiriting.")
        return redirect("apps:order-detail", order_number=order_number)
    try:
        with transaction.atomic():
            locked_order = Order.objects.select_for_update().get(pk=order.pk, user=request.user)
            if locked_order.status != Order.Status.DELIVERED:
                raise OrderActionError("Sharh faqat yetkazilgan buyurtma uchun yoziladi.")
            Review.objects.create(
                user=request.user,
                product=item.product,
                order=locked_order,
                rating=form.cleaned_data["rating"],
                text=form.cleaned_data["text"],
                is_verified_purchase=True,
            )
    except IntegrityError:
        messages.error(request, "Bu mahsulot uchun sharh allaqachon yozilgan.")
    except OrderActionError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Sharhingiz saqlandi.")
    return redirect("apps:order-detail", order_number=order_number)


@login_required
@require_POST
def request_return(request, order_number):
    order = get_object_or_404(Order, user=request.user, order_number=order_number)
    if order.status != Order.Status.DELIVERED:
        messages.error(request, "Qaytarish so‘rovi faqat yetkazilgan buyurtma uchun yuboriladi.")
        return redirect("apps:order-detail", order_number=order_number)
    form = ReturnRequestForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Qaytarish sababini kamida 10 ta belgi bilan kiriting.")
        return redirect("apps:order-detail", order_number=order_number)
    try:
        with transaction.atomic():
            locked_order = Order.objects.select_for_update().get(pk=order.pk, user=request.user)
            if locked_order.status != Order.Status.DELIVERED:
                raise OrderActionError("Qaytarish so‘rovi faqat yetkazilgan buyurtma uchun yuboriladi.")
            ReturnRequest.objects.create(
                order=locked_order,
                user=request.user,
                reason=form.cleaned_data["reason"],
            )
    except IntegrityError:
        messages.error(request, "Bu buyurtma uchun qaytarish so‘rovi allaqachon yuborilgan.")
    except OrderActionError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Qaytarish so‘rovi yuborildi.")
    return redirect("apps:order-detail", order_number=order_number)


class NotificationsView(LoginRequiredMixin, TemplateView):
    template_name = "notifications.html"
    extra_context = {"page_title": "Xabarnomalar — Zento", "active_page": "notifications"}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        notifications = self.request.user.notifications.order_by("-created_at")
        paginator = Paginator(notifications, 20)
        page_obj = paginator.get_page(self.request.GET.get("page"))
        context["notifications"] = page_obj
        context["page_obj"] = page_obj
        context["unread_count"] = notifications.filter(is_read=False).count()
        return context


@login_required
@require_POST
def mark_notification_read(request, notification_id):
    notification = get_object_or_404(Notification, pk=notification_id, user=request.user)
    notification.is_read = True
    notification.save(update_fields=["is_read", "updated_at"])
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"success": True, "unread_count": NotificationService.unread_count(request.user)})
    messages.success(request, "Xabar o‘qildi.")
    return redirect("apps:notifications")


@login_required
@require_POST
def mark_all_notifications_read(request):
    NotificationService.mark_read(request.user)
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"success": True, "unread_count": 0})
    messages.success(request, "Barcha xabarlar o‘qildi.")
    return redirect("apps:notifications")


class ChatView(LoginRequiredMixin, TemplateView):
    template_name = "chat.html"
    extra_context = {"page_title": "Yordam chat — Zento", "active_page": "chat"}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        chats = (
            self.request.user.chats.select_related("seller", "order", "product")
            .prefetch_related("messages__sender")
            .order_by("-updated_at")
        )
        active_chat_id = self.request.GET.get("chat")
        active_chat = None
        if active_chat_id:
            active_chat = chats.filter(pk=active_chat_id).first()
        if active_chat is None:
            active_chat = chats.first()
        if active_chat:
            ChatService.mark_received_messages_read(active_chat, self.request.user)
        context["chats"] = chats
        context["active_chat"] = active_chat
        context["active_chat_id"] = active_chat.pk if active_chat else None
        return context


@login_required
@require_POST
def create_chat(request):
    subject = (request.POST.get("subject") or "Zento yordam").strip()[:200]
    text = request.POST.get("message", "").strip()
    seller_id = request.POST.get("seller_id")
    order_number = request.POST.get("order_number")
    product_id = request.POST.get("product_id")
    seller = None
    order = None
    product = None
    if seller_id:
        seller = get_object_or_404(Seller, pk=seller_id, is_active=True)
    if order_number:
        order = get_object_or_404(Order, user=request.user, order_number=order_number)
    if product_id:
        product = get_object_or_404(Product, pk=product_id, is_active=True)
        if seller and product.seller_id != seller.pk:
            return JsonResponse({"success": False, "error": "Sotuvchi mahsulotga mos kelmaydi."}, status=400)
        seller = seller or product.seller
    chat = ChatService.create_chat(request.user, subject=subject, seller=seller, order=order, product=product)
    if text:
        try:
            ChatService.send_message(chat, request.user, text)
        except ValueError as exc:
            chat.delete()
            return JsonResponse({"success": False, "error": str(exc)}, status=400)
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({
            "success": True,
            "chat_id": chat.pk,
            "subject": chat.subject,
            "url": reverse_lazy("apps:chat") + f"?chat={chat.pk}",
        })
    return redirect(f"{reverse_lazy('apps:chat')}?chat={chat.pk}")


@login_required
@require_POST
def send_chat_message(request):
    chat_id = request.POST.get("chat_id")
    text = request.POST.get("message", "").strip()
    chat = ChatService.get_user_chat(request.user, chat_id)
    if chat is None:
        return JsonResponse({"success": False, "error": "Suhbat topilmadi."}, status=404)
    try:
        message = ChatService.send_message(chat, request.user, text)
    except ValueError as exc:
        return JsonResponse({"success": False, "error": str(exc)}, status=400)
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({
            "success": True,
            "message_id": message.pk,
            "text": message.text,
            "sender_id": message.sender_id,
            "created_at": message.created_at.isoformat(),
        })
    return redirect(f"{reverse_lazy('apps:chat')}?chat={chat.pk}")


@login_required
def fetch_chat_messages(request, chat_id):
    chat = ChatService.get_user_chat(request.user, chat_id)
    if chat is None:
        return JsonResponse({"success": False, "error": "Suhbat topilmadi."}, status=404)
    ChatService.mark_received_messages_read(chat, request.user)
    since_id = request.GET.get("since")
    queryset = chat.messages.select_related("sender").order_by("created_at")
    if since_id:
        try:
            queryset = queryset.filter(pk__gt=int(since_id))
        except ValueError:
            queryset = queryset.none()
    messages_list = [{
        "id": message.pk,
        "sender_id": message.sender_id,
        "text": message.text,
        "is_read": message.is_read,
        "created_at": message.created_at.isoformat(),
        "is_mine": message.sender_id == request.user.pk,
    } for message in queryset]
    return JsonResponse({"success": True, "messages": messages_list, "chat_id": chat.pk})


class ContactView(FormView):
    template_name = "contact.html"
    form_class = ContactForm
    success_url = reverse_lazy("apps:contact")
    extra_context = {"page_title": "Kontaktlar — Zento"}

    def form_valid(self, form):
        message = form.save()
        send_mail(
            subject=f"[Zento] {dict(ContactMessage.SUBJECT_CHOICES).get(message.subject, 'Boshqa')}",
            message=f"Ism: {message.full_name}\nEmail: {message.email}\n\n{message.message}",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[settings.DEFAULT_FROM_EMAIL],
            fail_silently=True,
        )
        messages.success(self.request, "Murojaatingiz muvaffaqiyatli yuborildi.")
        return redirect("apps:contact")


class FAQView(TemplateView):
    template_name = "faq.html"
    extra_context = {"page_title": "Yordam markazi — Zento"}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["faq_categories"] = [
            {"id": "all", "label": "Barchasi"},
            {"id": "order", "label": "Buyurtma"},
            {"id": "shipping", "label": "Yetkazish"},
            {"id": "return", "label": "Qaytarish"},
            {"id": "payment", "label": "To‘lov"},
        ]
        context["faq_items"] = [
            {"category": "order", "question": "Buyurtmani qanday rasmiylashtiraman?", "answer": "Mahsulotni savatga qo‘shing, yetkazib berish usulini va to‘lov turini tanlang, so‘ng tasdiqlang."},
            {"category": "order", "question": "Buyurtma holatini qayerdan ko‘raman?", "answer": "Shaxsiy kabinetdagi “Buyurtmalar” bo‘limida har bir bosqich ko‘rinadi."},
            {"category": "return", "question": "Mahsulotni qaytarish mumkinmi?", "answer": "Foydalanilmagan mahsulotni belgilangan muddat ichida punkt orqali qaytarish mumkin. Ayrim toifalarda istisnolar bor."},
            {"category": "payment", "question": "Muddatli to‘lov qanday ishlaydi?", "answer": "Zento Pay tasdiqlangach, xarid summasi tanlangan muddatga teng qismlarga bo‘linadi."},
            {"category": "order", "question": "Sotuvchi bilan qanday bog‘lanaman?", "answer": "Mahsulot yoki buyurtma sahifasidan chatni oching. Marketplace administratori ham yordam bera oladi."},
            {"category": "shipping", "question": "Promokod nega ishlamadi?", "answer": "Amal qilish muddati, minimal summa va qatnashuvchi mahsulotlarni tekshiring."},
        ]
        return context


class CheckoutView(LoginRequiredMixin, TemplateView):
    template_name = "checkout.html"
    extra_context = {
        "page_title": "Buyurtmani rasmiylashtirish — Zento",
        "compact_layout": True,
    }

    def dispatch(self, request, *args, **kwargs):
        cart = CartService.get_cart(request.user) if request.user.is_authenticated else None
        if request.user.is_authenticated and not cart.items.exists():
            return redirect("apps:cart")
        return super().dispatch(request, *args, **kwargs)

    def get_form(self):
        if not hasattr(self, "_checkout_form"):
            initial = {
                "first_name": self.request.user.first_name,
                "last_name": self.request.user.last_name,
                "phone": self.request.user.phone,
                "email": self.request.user.email,
                "delivery_type": self.request.GET.get("delivery_type", "pickup"),
                "delivery_point": (
                    self.request.GET.get("delivery_point")
                    or self.request.session.get("selected_delivery_point")
                    or None
                ),
                "payment_type": "card",
            }
            self._checkout_form = CheckoutForm(
                self.request.user,
                data=self.request.POST or None,
                initial=initial,
            )
        return self._checkout_form

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cart = CartService.get_cart(self.request.user)
        items, cart_count, cart_total = CartService.summary(cart)
        context.update({
            "form": kwargs.get("form", self.get_form()),
            "cart_items": items,
            "cart_count": cart_count,
            "cart_total": cart_total,
            "delivery_points": DeliveryPoint.objects.filter(is_active=True).order_by("name"),
        })
        return context

    def post(self, request, *args, **kwargs):
        form = self.get_form()
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))

        cleaned = form.cleaned_data
        try:
            order = CheckoutService.place_order(request.user, cleaned)
        except CheckoutError as exc:
            form.add_error(None, str(exc))
            return self.render_to_response(self.get_context_data(form=form))
        request.user.first_name = cleaned["first_name"]
        request.user.last_name = cleaned["last_name"]
        request.user.phone = cleaned["phone"]
        request.user.save(update_fields=["first_name", "last_name", "phone"])
        request.session["checkout_success_order"] = order.order_number
        request.session.modified = True
        return redirect("apps:success")


class SuccessView(LoginRequiredMixin, TemplateView):
    template_name = "success.html"
    extra_context = {
        "page_title": "Buyurtma qabul qilindi — Zento",
        "compact_layout": True,
    }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order_number = (
            self.request.GET.get("order", "").strip()
            or self.request.session.pop("checkout_success_order", "")
        )
        order = get_object_or_404(
            Order.objects.select_related("address", "delivery_point", "payment"),
            user=self.request.user,
            order_number=order_number,
        )
        context["order"] = order
        context["order_items"] = order.items.select_related("seller", "variant")
        return context


class PickupView(TemplateView):
    template_name = "pickup.html"
    extra_context = {"page_title": "Topshirish punktlari — Zento"}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        query = self.request.GET.get("q", "").strip()
        region = self.request.GET.get("region", "").strip()
        city = self.request.GET.get("city", "").strip()
        points = DeliveryPoint.objects.filter(is_active=True)
        if region:
            points = points.filter(region=region)
        if city:
            points = points.filter(city=city)
        if query:
            points = points.filter(Q(name__icontains=query) | Q(address__icontains=query))
        map_points = [
            {
                "id": point.pk,
                "name": point.name,
                "region": point.region,
                "city": point.city,
                "address": point.address,
                "working_hours": point.working_hours,
                "latitude": float(point.latitude) if point.latitude is not None else None,
                "longitude": float(point.longitude) if point.longitude is not None else None,
            }
            for point in points.order_by("name")
        ]
        context.update({
            "delivery_points": points.order_by("name"),
            "map_points": map_points,
            "yandex_maps_api_key": settings.YANDEX_MAPS_API_KEY,
            "query": query,
            "region": region,
            "city": city,
            "regions": DeliveryPoint.objects.filter(is_active=True)
            .exclude(region="")
            .values_list("region", flat=True)
            .distinct()
            .order_by("region"),
            "cities": DeliveryPoint.objects.filter(is_active=True, region=region)
            .exclude(city="")
            .values_list("city", flat=True)
            .distinct()
            .order_by("city") if region else [],
        })
        return context


@require_POST
def pickup_continue(request):
    if not request.user.is_authenticated:
        return redirect(f"{reverse_lazy('apps:login')}?{urlencode({'next': reverse_lazy('apps:pickup')})}")
    point_id = request.POST.get("delivery_point")
    point = get_object_or_404(DeliveryPoint, pk=point_id, is_active=True)
    request.session["selected_delivery_point"] = point.pk
    request.session.modified = True
    return redirect(
        f"{reverse_lazy('apps:checkout')}?delivery_type=pickup&delivery_point={point.pk}"
    )


class ProductCreateView(SellerRequiredMixin, FormView):
    template_name = "product-create.html"
    form_class = ProductCreateForm
    extra_context = {"page_title": "Yangi mahsulot — Zento", "active_page": "seller-products"}

    def form_valid(self, form):
        seller = self.seller
        data = form.cleaned_data
        base_slug = slugify(data["name"]) or "product"
        product_slug = base_slug
        suffix = 2
        while Product.objects.filter(slug=product_slug).exists():
            product_slug = f"{base_slug}-{suffix}"
            suffix += 1

        sku = f"ZT-{base_slug[:40].upper()}-{secrets.token_hex(3).upper()}"
        with transaction.atomic():
            brand = None
            if data["brand"].strip():
                brand = Brand.objects.filter(name__iexact=data["brand"].strip()).first()
                if brand is None:
                    brand = Brand.objects.create(name=data["brand"].strip())
            product = Product.objects.create(
                seller=seller,
                category=data["category"],
                store=seller.shop_store,
                name=data["name"].strip(),
                slug=product_slug,
                brand=brand,
                sku=sku,
                price=data["price"],
                old_price=data["old_price"],
                stock=data["stock"],
                description=data["description"].strip(),
                # Older clients did not send this newly added checkbox; keep
                # their products visible while allowing an explicit unchecked
                # choice in the seller form.
                is_active=data["is_active"] if "is_active" in self.request.POST else True,
            )
            for index, (variant_name, extra_price) in enumerate(data["variants"], start=1):
                ProductVariant.objects.create(
                    product=product,
                    name=variant_name,
                    sku=f"{sku}-V{index}",
                    extra_price=extra_price,
                    stock=data["stock"],
                )
        messages.success(self.request, "Mahsulot yaratildi.")
        return redirect("apps:product", slug=product.slug)


class SellerProductEditView(SellerRequiredMixin, FormView):
    template_name = "seller-product-edit.html"
    form_class = ProductUpdateForm
    extra_context = {"page_title": "Mahsulotni tahrirlash — Zento", "active_page": "seller-products"}

    def get_product(self):
        return get_object_or_404(Product, pk=self.kwargs["product_id"], seller=self.seller)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["instance"] = self.get_product()
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product = self.get_product()
        context.update({
            "product": product,
            "variants": product.variants.order_by("id"),
            "variant_form": ProductVariantForm(),
        })
        return context

    def form_valid(self, form):
        product = self.get_product()
        data = form.cleaned_data
        brand = None
        if data["brand"].strip():
            brand, _ = Brand.objects.get_or_create(name=data["brand"].strip())
        product.category = data["category"]
        product.name = data["name"].strip()
        product.brand = brand
        product.price = data["price"]
        product.old_price = data["old_price"]
        product.stock = data["stock"]
        product.description = data["description"].strip()
        product.is_active = data["is_active"]
        product.save()
        messages.success(self.request, "Mahsulot ma’lumotlari saqlandi.")
        return redirect("apps:seller-product-edit", product_id=product.pk)


@login_required
@require_POST
def seller_product_variant_save(request, product_id, variant_id=None):
    seller = get_shop_admin_seller(request)
    product = get_object_or_404(Product, pk=product_id, seller=seller)
    variant = get_object_or_404(ProductVariant, pk=variant_id, product=product) if variant_id else ProductVariant(product=product)
    form = ProductVariantForm(request.POST, instance=variant)
    if form.is_valid():
        variant = form.save(commit=False)
        variant.product = product
        if not variant.pk:
            variant.sku = f"{product.sku}-V{secrets.token_hex(3).upper()}"
        variant.save()
        messages.success(request, "Variant saqlandi.")
    else:
        messages.error(request, "Variant ma’lumotlarini tekshiring.")
    return redirect("apps:seller-product-edit", product_id=product.pk)


@login_required
@require_POST
def seller_product_variant_delete(request, product_id, variant_id):
    seller = get_shop_admin_seller(request)
    product = get_object_or_404(Product, pk=product_id, seller=seller)
    get_object_or_404(ProductVariant, pk=variant_id, product=product).delete()
    messages.success(request, "Variant o‘chirildi.")
    return redirect("apps:seller-product-edit", product_id=product.pk)


@login_required
@require_POST
def seller_product_delete(request, product_id):
    seller = get_shop_admin_seller(request)
    product = get_object_or_404(Product, pk=product_id, seller=seller)
    try:
        product.delete()
    except ProtectedError:
        messages.error(request, "Buyurtma tarixida mavjud mahsulotni o‘chirib bo‘lmaydi.")
    else:
        messages.success(request, "Mahsulot o‘chirildi.")
    return redirect("apps:seller-products")


class SellerOrdersView(SellerRequiredMixin, TemplateView):
    template_name = "seller-orders.html"
    extra_context = {"page_title": "Do‘kon buyurtmalari — Zento", "active_page": "seller-orders"}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        orders = SellerOrder.objects.filter(seller=self.seller).select_related(
            "order", "order__user"
        ).prefetch_related(
            Prefetch(
                "order__items",
                queryset=OrderItem.objects.filter(seller=self.seller).select_related("product", "variant"),
            )
        ).order_by("-created_at")
        status = self.request.GET.get("status", "").strip()
        if status in Order.Status.values:
            orders = orders.filter(status=status)
        else:
            status = ""
        status_labels = dict(Order.Status.choices)
        paginator = Paginator(orders, 15)
        page_obj = paginator.get_page(self.request.GET.get("page"))
        for seller_order in page_obj:
            seller_order.available_transitions = [
                {"value": value, "label": status_labels[value]}
                for value in SellerOrderService.ALLOWED_TRANSITIONS.get(seller_order.status, ())
            ]
            seller_order.shop_items = list(seller_order.order.items.all())
        context.update({
            "orders": page_obj,
            "page_obj": page_obj,
            "selected_status": status,
            "order_statuses": Order.Status.choices,
            "allowed_transitions": SellerOrderService.ALLOWED_TRANSITIONS,
        })
        return context


class SellerCustomersView(SellerRequiredMixin, TemplateView):
    template_name = "seller-customers.html"
    extra_context = {"page_title": "Mijozlar — Zento", "active_page": "seller-customers"}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        shop_orders = SellerOrder.objects.filter(seller=self.seller)
        customer_ids = shop_orders.values("order__user_id").distinct()
        customers = User.objects.filter(pk__in=Subquery(customer_ids)).annotate(
            shop_order_count=Count(
                "orders__seller_orders",
                filter=Q(orders__seller_orders__seller=self.seller),
                distinct=True,
            ),
            last_shop_order=Max(
                "orders__created_at",
                filter=Q(orders__seller_orders__seller=self.seller),
            ),
        ).order_by("email")
        context.update({
            "seller": self.seller,
            "customers": customers,
            "customer_count": customers.count(),
        })
        return context


class SellerOrderDetailView(SellerRequiredMixin, TemplateView):
    template_name = "seller-order-detail.html"
    extra_context = {"page_title": "Buyurtma tafsilotlari — Zento", "active_page": "seller-orders"}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        seller_order = get_object_or_404(
            SellerOrder.objects.filter(
                seller=self.seller,
                order__order_number=self.kwargs["order_number"],
            ).select_related(
                "seller",
                "order",
                "order__user",
                "order__address",
                "order__delivery_point",
            )
        )
        seller_order.shop_items = list(
            seller_order.order.items.filter(seller=self.seller).select_related("product", "variant")
        )
        status_labels = dict(Order.Status.choices)
        seller_order.available_transitions = [
            {"value": value, "label": status_labels[value]}
            for value in SellerOrderService.ALLOWED_TRANSITIONS.get(seller_order.status, ())
        ]
        context["shop_order"] = seller_order
        return context


@login_required
@require_POST
def seller_order_update_status(request, order_number):
    seller = get_shop_admin_seller(request)
    try:
        SellerOrderService.update_status(
            seller,
            order_number,
            request.POST.get("status"),
            changed_by=request.user,
        )
    except OrderActionError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Buyurtma holati yangilandi.")
    return redirect("apps:seller-orders")


class WishlistPageView(LoginRequiredMixin, TemplateView):
    template_name = "wishlist.html"
    extra_context = {"page_title": "Sevimlilar — Zento", "active_page": "wishlist"}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product_ids = list(
            Wishlist.objects.filter(user=self.request.user)
            .values_list("product_id", flat=True)
        )
        products = (
            Product.objects.filter(
                pk__in=product_ids,
                seller__is_active=True,
            )
            .select_related("brand", "category", "seller")

            .annotate(
                average_rating=Coalesce(Avg("reviews__rating"), Value(0.0)),
                review_count=Count("reviews", distinct=True),
            )
        )

        context.update({
            "products": products,
            "product_count": products.count(),
        })
        return context


@require_http_methods(["POST"])
def wishlist_toggle(request, product_id):
    if not request.user.is_authenticated:
        next_url = request.META.get("HTTP_REFERER") or reverse_lazy("apps:wishlist")
        login_url = f"{reverse_lazy('apps:login')}?{urlencode({'next': next_url})}"
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({
                "success": False,
                "error": "Kirish talab qilinadi.",
                "login_url": login_url,
            }, status=401)
        return redirect(login_url)

    product = get_object_or_404(Product, pk=product_id, is_active=True)
    wishlist_item, created = Wishlist.objects.get_or_create(
        user=request.user,
        product=product,
    )
    if not created:
        wishlist_item.delete()
        is_in_wishlist = False
    else:
        is_in_wishlist = True

    return JsonResponse({
        "success": True,
        "is_in_wishlist": is_in_wishlist,
        "wishlist_count": request.user.wishlist_items.count(),
    })


@require_http_methods(["POST"])
def compare_add(request):
    product_id = request.POST.get("product_id")
    if not product_id:
        return JsonResponse({"success": False, "error": "product_id required"}, status=400)

    product = get_object_or_404(Product, pk=product_id, is_active=True)

    if "compare_items" not in request.session:
        request.session["compare_items"] = {}

    compare_items = request.session["compare_items"]
    category_id = str(product.category_id)

    if category_id not in compare_items:
        compare_items[category_id] = []

    if str(product_id) not in compare_items[category_id]:
        if len(compare_items[category_id]) >= 4:
            return JsonResponse({
                "success": False,
                "error": "Bu kategoriyada maksimal 4 ta mahsulot taqqoslash mumkin.",
            }, status=400)
        compare_items[category_id].append(str(product_id))

    request.session.modified = True

    return JsonResponse({
        "success": True,
        "compare_count": sum(len(v) for v in compare_items.values()),
    })


@require_http_methods(["POST"])
def compare_remove(request):
    product_id = request.POST.get("product_id")
    if not product_id:
        return JsonResponse({"success": False, "error": "product_id required"}, status=400)

    if "compare_items" in request.session:
        compare_items = request.session["compare_items"]
        for category_id in list(compare_items.keys()):
            if str(product_id) in compare_items[category_id]:
                compare_items[category_id].remove(str(product_id))
                if not compare_items[category_id]:
                    del compare_items[category_id]
        request.session.modified = True

    return JsonResponse({
        "success": True,
        "compare_count": sum(len(v) for v in request.session.get("compare_items", {}).values()),
    })


@require_http_methods(["POST"])
def compare_clear(request):
    if "compare_items" in request.session:
        del request.session["compare_items"]
        request.session.modified = True

    return JsonResponse({"success": True})


class ComparePageView(TemplateView):
    template_name = "compare.html"
    extra_context = {"page_title": "Mahsulotlarni taqqoslash — Zento"}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        compare_items = self.request.session.get("compare_items", {})
        all_product_ids = []
        for product_ids in compare_items.values():
            all_product_ids.extend(int(product_id) for product_id in product_ids)

        products = []
        if all_product_ids:
            product_map = {
                product.pk: product
                for product in Product.objects.filter(
                    pk__in=all_product_ids,
                    is_active=True,
                    seller__is_active=True,
                ).filter(Q(store__isnull=True) | Q(store__is_active=True))
                .select_related("brand", "category", "seller")
                .prefetch_related("variants")
                .annotate(
                    average_rating=Coalesce(Avg("reviews__rating"), Value(0.0)),
                    review_count=Count("reviews", distinct=True),
                )
            }
            products = [product_map[product_id] for product_id in all_product_ids if product_id in product_map]

        context.update({
            "products": products,
            "product_count": len(products),
            "compare_product_ids": [product.pk for product in products],
        })
        return context
