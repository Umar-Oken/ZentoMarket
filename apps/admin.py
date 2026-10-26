from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .forms import AdminUserCreationForm
from .services import delete_store_preserving_history
from .models import (
    Address, Brand, Cart, CartItem, Category, Chat, ChatMessage, ContactMessage,
    DeliveryPoint, Notification, Order, OrderItem, Payment, Product,
    ProductVariant, Review, ReturnRequest, Seller, SellerApplication, SellerOrder,
    SellerOrderStatusHistory, Store, User, Wishlist,
)


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    add_form = AdminUserCreationForm
    list_display = ("email", "first_name", "last_name", "role", "is_staff", "is_active")
    list_filter = ("role", "is_staff", "is_active", "date_joined")
    search_fields = ("email", "first_name", "last_name", "phone")
    ordering = ("-date_joined",)
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Shaxsiy ma’lumotlar", {"fields": ("first_name", "last_name", "phone", "avatar", "role")}),
        ("Ruxsatlar", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Sanalar", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "first_name",
                    "last_name",
                    "phone",
                    "role",
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "password1",
                    "password2",
                ),
            },
        ),
    )
    readonly_fields = ("last_login", "date_joined")


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "store", "seller", "price", "stock", "product_status", "created_at")
    list_filter = ("category", "store", "seller", "is_active", "brand")
    search_fields = ("name", "sku", "brand__name")
    prepopulated_fields = {"slug": ("name",)}
    inlines = (ProductVariantInline,)

    @admin.display(description="Holat")
    def product_status(self, obj):
        return obj.status_display


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "image_preview", "store", "parent", "is_active", "created_at")
    list_filter = ("is_active", "parent", "store")
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("image_preview",)

    @admin.display(description="Rasm")
    def image_preview(self, obj):
        if not obj.image:
            return "Rasm mavjud emas"
        return format_html(
            '<img src="{}" alt="{}" style="max-width:160px;max-height:100px;object-fit:cover;">',
            obj.image.url,
            obj.name,
        )


@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = ("name", "shop_code", "shop_admin_email", "is_active", "created_at")
    list_filter = ("is_active", "seller")
    search_fields = ("name", "shop_code", "email", "seller__user__email")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("shop_code", "email", "created_at", "updated_at")

    @admin.display(description="Shop admin emaili")
    def shop_admin_email(self, obj):
        return obj.seller.user.email if obj.seller_id else obj.email

    def delete_model(self, request, obj):
        delete_store_preserving_history(obj)

    def delete_queryset(self, request, queryset):
        for store in queryset.select_related("seller").iterator():
            delete_store_preserving_history(store)


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Seller)
class SellerAdmin(admin.ModelAdmin):
    list_display = ("store_name", "code", "shop_code", "seller_email", "rating", "is_verified", "is_active")
    list_filter = ("is_verified", "is_active")
    search_fields = ("store_name", "code", "user__email", "phone")

    @admin.display(description="Email", ordering="user__email")
    def seller_email(self, obj):
        return obj.user.email

    @admin.display(description="Shop code")
    def shop_code(self, obj):
        shop = getattr(obj, "shop_store", None)
        return shop.shop_code if shop else "Shop yozuvi mavjud emas"


@admin.register(SellerApplication)
class SellerApplicationAdmin(admin.ModelAdmin):
    list_display = ("store_name", "user", "phone", "category", "estimated_product_count", "status", "created_at")
    list_filter = ("status", "category", "created_at")
    search_fields = ("store_name", "user__email", "full_name", "phone")
    readonly_fields = ("user", "full_name", "phone", "store_name", "category", "estimated_product_count", "created_at", "updated_at")


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("product_name", "price", "seller")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("order_number", "user", "total", "status", "delivery_type", "payment_type", "created_at")
    list_filter = ("status", "delivery_type", "payment_type", "created_at")
    search_fields = ("order_number", "user__email")
    readonly_fields = ("order_number", "created_at", "updated_at")
    inlines = (OrderItemInline,)


@admin.register(SellerOrder)
class SellerOrderAdmin(admin.ModelAdmin):
    list_display = ("order", "seller", "status", "created_at", "updated_at")
    list_filter = ("status", "seller")
    search_fields = ("order__order_number", "seller__store_name", "seller__user__email")
    readonly_fields = ("created_at", "updated_at")


@admin.register(SellerOrderStatusHistory)
class SellerOrderStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ("seller_order", "old_status", "new_status", "changed_by", "changed_at")
    list_filter = ("old_status", "new_status", "changed_at")
    search_fields = ("seller_order__order__order_number", "seller_order__seller__store_name")
    readonly_fields = ("seller_order", "old_status", "new_status", "changed_by", "changed_at")


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("user", "created_at", "updated_at")
    search_fields = ("user__email",)


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ("cart", "product", "variant", "quantity", "price")
    search_fields = ("cart__user__email", "product__name")


@admin.register(Wishlist)
class WishlistAdmin(admin.ModelAdmin):
    list_display = ("user", "product", "created_at")
    search_fields = ("user__email", "product__name")


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ("user", "title", "city", "street", "is_default")
    list_filter = ("city", "is_default")
    search_fields = ("user__email", "city", "street", "phone")


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("product", "user", "rating", "is_verified_purchase", "created_at")
    list_filter = ("rating", "is_verified_purchase", "created_at")
    search_fields = ("product__name", "user__email", "text")


@admin.register(ReturnRequest)
class ReturnRequestAdmin(admin.ModelAdmin):
    list_display = ("order", "user", "status", "created_at", "updated_at")
    list_filter = ("status", "created_at")
    search_fields = ("order__order_number", "user__email", "reason")


@admin.register(DeliveryPoint)
class DeliveryPointAdmin(admin.ModelAdmin):
    list_display = ("name", "region", "city", "address", "phone", "working_hours", "is_active")
    list_filter = ("region", "city", "is_active")
    search_fields = ("name", "region", "city", "address", "phone")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("order", "provider", "transaction_id", "amount", "status", "paid_at")
    list_filter = ("provider", "status", "paid_at")
    search_fields = ("order__order_number", "transaction_id")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("user", "title", "notification_type", "is_read", "created_at")
    list_filter = ("notification_type", "is_read", "created_at")
    search_fields = ("user__email", "title", "message")


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ("full_name", "email", "subject", "is_answered", "created_at")
    list_filter = ("subject", "is_answered", "created_at")
    search_fields = ("full_name", "email", "message")


class ChatMessageInline(admin.TabularInline):
    model = ChatMessage
    extra = 1


@admin.register(Chat)
class ChatAdmin(admin.ModelAdmin):
    list_display = ("user", "seller", "order", "product", "subject", "created_at")
    list_filter = ("seller", "created_at")
    search_fields = ("user__email", "subject", "product__name", "order__order_number")
    inlines = (ChatMessageInline,)


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ("product", "name", "sku", "extra_price", "stock", "is_active")
    list_filter = ("is_active",)
    search_fields = ("product__name", "name", "sku")
