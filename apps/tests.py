from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils.text import slugify

from .models import (
    Brand,
    Cart,
    CartItem,
    Category,
    Order,
    OrderItem,
    Product,
    ProductVariant,
    Review,
    Seller,
    User,
    Wishlist,
)


class AuthenticationFlowTests(TestCase):
    password = "StrongPass2026!"

    def setUp(self):
        self.user = User.objects.create_user(
            email="aziza@example.com",
            username="aziza",
            password=self.password,
            first_name="Aziza",
            last_name="Karimova",
            phone="+998901234567",
        )

    def test_main_page_is_public(self):
        response = self.client.get(reverse("apps:index"))
        self.assertEqual(response.status_code, 200)

    def test_checkout_redirects_anonymous_user_to_login(self):
        response = self.client.get(reverse("apps:checkout"))
        expected = f"{reverse('apps:login')}?next={reverse('apps:checkout')}"
        self.assertRedirects(response, expected)

    def test_login_uses_email_and_redirects_to_next(self):
        response = self.client.post(
            reverse("apps:login"),
            {"username": self.user.email.upper(), "password": self.password, "next": reverse("apps:checkout")},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("apps:checkout"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_authenticated_user_is_redirected_away_from_login(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("apps:login"))
        self.assertRedirects(response, reverse("apps:index"))

    def test_authenticated_user_is_redirected_away_from_registration(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("apps:signup"))
        self.assertRedirects(response, reverse("apps:index"))

    def test_registration_creates_customer_and_logs_in(self):
        response = self.client.post(reverse("apps:signup"), {
            "first_name": "Dilnoza",
            "last_name": "Rahimova",
            "email": "DILNOZA@example.com",
            "phone": "+998 91 234 56 78",
            "password1": self.password,
            "password2": self.password,
        })
        new_user = User.objects.get(email="dilnoza@example.com")
        self.assertRedirects(response, reverse("apps:index"))
        self.assertTrue(new_user.check_password(self.password))
        self.assertEqual(new_user.role, User.Role.CUSTOMER)
        self.assertEqual(new_user.phone, "+998912345678")
        self.assertEqual(int(self.client.session["_auth_user_id"]), new_user.pk)

    def test_registration_rejects_duplicate_email(self):
        response = self.client.post(reverse("apps:signup"), {
            "first_name": "Aziza",
            "last_name": "Karimova",
            "email": "AZIZA@example.com",
            "phone": "+998 90 765 43 21",
            "password1": self.password,
            "password2": self.password,
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bu email bilan hisob allaqachon mavjud.")
        self.assertEqual(User.objects.filter(email__iexact="aziza@example.com").count(), 1)

    def test_registration_from_checkout_returns_to_checkout(self):
        response = self.client.post(reverse("apps:signup"), {
            "first_name": "Madina",
            "last_name": "Aliyeva",
            "email": "madina@example.com",
            "phone": "+998 93 111 22 33",
            "password1": self.password,
            "password2": self.password,
            "next": reverse("apps:checkout"),
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("apps:checkout"))

    def test_authenticated_user_can_open_checkout(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("apps:checkout"))
        self.assertRedirects(response, reverse("apps:cart"))

    def test_logout_accepts_post_and_returns_to_main_page(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("apps:logout"))
        self.assertRedirects(response, reverse("apps:index"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_new_user_cart_is_empty_and_does_not_use_another_users_cart(self):
        seller_user = User.objects.create_user(
            email="cart-seller@example.com",
            username="cart-seller",
            password=self.password,
            role=User.Role.SELLER,
        )
        seller = Seller.objects.create(user=seller_user, store_name="Cart Seller")
        category = Category.objects.create(name="Cart Category", slug="cart-category")
        product = Product.objects.create(
            seller=seller,
            category=category,
            name="Cart product",
            slug="cart-product",
            sku="CART-PRODUCT",
            price=Decimal("100000"),
            stock=5,
        )
        other_user = User.objects.create_user(
            email="other@example.com",
            username="other",
            password=self.password,
        )
        other_cart = Cart.objects.create(user=other_user)
        CartItem.objects.create(
            cart=other_cart,
            product=product,
            price=product.price,
            quantity=2,
        )

        self.client.force_login(self.user)
        response = self.client.get(reverse("apps:cart"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["cart_items"], [])
        self.assertEqual(response.context["cart_count"], 0)
        self.assertContains(response, "Savatingiz bo‘sh")
        self.assertNotContains(response, product.name)
        self.assertContains(response, 'data-cart-count>0</b>', status_code=200)


class StorefrontTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.customer = User.objects.create_user(
            email="customer@example.com",
            username="customer",
            password="StrongPass2026!",
        )
        seller_user = User.objects.create_user(
            email="seller@example.com",
            username="seller",
            password="StrongPass2026!",
            role=User.Role.SELLER,
        )
        cls.seller = Seller.objects.create(user=seller_user, store_name="Tech Store")
        cls.electronics = Category.objects.create(name="Elektronika", slug="elektronika")
        cls.phones = Category.objects.create(
            name="Smartfonlar", slug="smartfonlar", parent=cls.electronics
        )
        audio = Category.objects.create(name="Audio", slug="audio", parent=cls.electronics)
        samsung = Brand.objects.create(name="Samsung", slug="samsung")
        sony = Brand.objects.create(name="Sony", slug="sony")
        cls.discount_product = Product.objects.create(
            seller=cls.seller,
            category=cls.phones,
            brand=samsung,
            name="Samsung Galaxy Test",
            slug="samsung-galaxy-test",
            sku="TEST-SAMSUNG",
            description="5G smartfon",
            price=Decimal("800000"),
            old_price=Decimal("1000000"),
            stock=10,
        )
        cls.best_seller = Product.objects.create(
            seller=cls.seller,
            category=audio,
            brand=sony,
            name="Sony Headphones Test",
            slug="sony-headphones-test",
            sku="TEST-SONY",
            price=Decimal("1200000"),
            stock=10,
        )
        order = Order.objects.create(
            user=cls.customer,
            order_number="ZT-TEST-1",
            status=Order.Status.DELIVERED,
        )
        OrderItem.objects.create(
            order=order,
            product=cls.discount_product,
            seller=cls.seller,
            product_name=cls.discount_product.name,
            price=cls.discount_product.price,
            quantity=1,
        )
        OrderItem.objects.create(
            order=order,
            product=cls.best_seller,
            seller=cls.seller,
            product_name=cls.best_seller.name,
            price=cls.best_seller.price,
            quantity=5,
        )
        Review.objects.create(
            user=cls.customer,
            product=cls.discount_product,
            order=order,
            rating=5,
            text="A'lo mahsulot",
        )
        Review.objects.create(
            user=cls.customer,
            product=cls.best_seller,
            order=order,
            rating=3,
            text="Yaxshi",
        )

    def test_homepage_uses_dynamic_catalog_and_product_sections(self):
        response = self.client.get(reverse("apps:index"))

        self.assertContains(response, "Smartfonlar")
        self.assertContains(response, self.discount_product.name)
        self.assertEqual(response.context["best_sellers"][0], self.best_seller)
        self.assertEqual(response.context["popular_brands"][0].name, "Sony")

    def test_search_finds_products_by_name_case_insensitively(self):
        response = self.client.get(reverse("apps:search"), {"q": "galaxy"})

        self.assertContains(response, self.discount_product.name)
        self.assertNotContains(response, self.best_seller.name)
        self.assertEqual(response.context["result_count"], 1)

    def test_search_can_filter_by_category_brand_and_discount(self):
        category_response = self.client.get(reverse("apps:search"), {"category": "audio"})
        brand_response = self.client.get(reverse("apps:search"), {"brand": "samsung"})
        discount_response = self.client.get(reverse("apps:search"), {"discount": "1"})

        self.assertContains(category_response, self.best_seller.name)
        self.assertContains(brand_response, self.discount_product.name)
        self.assertContains(discount_response, self.discount_product.name)
        self.assertNotContains(discount_response, self.best_seller.name)

    def test_catalog_lists_database_categories(self):
        response = self.client.get(reverse("apps:catalog"))

        self.assertContains(response, "Smartfonlar")
        self.assertContains(response, "Audio")

    def test_category_url_uses_slug_and_database_context(self):
        response = self.client.get(
            reverse("apps:category", kwargs={"slug": self.phones.slug})
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["category"], self.phones)
        self.assertEqual(response.context["parent_category"], self.electronics)
        self.assertEqual(
            [item.slug for item in response.context["breadcrumbs"]],
            ["elektronika", "smartfonlar"],
        )
        self.assertEqual(response.context["product_count"], 1)
        self.assertContains(response, self.discount_product.name)

    def test_parent_category_includes_descendant_products_and_children(self):
        response = self.client.get(
            reverse("apps:category", kwargs={"slug": self.electronics.slug})
        )

        self.assertEqual(response.context["product_count"], 2)
        self.assertContains(response, "Smartfonlar")
        self.assertContains(response, "Audio")
        self.assertContains(response, self.discount_product.name)
        self.assertContains(response, self.best_seller.name)

    def test_inactive_and_out_of_stock_products_are_excluded_from_category(self):
        Product.objects.create(
            seller=self.seller,
            category=self.phones,
            name="Inactive phone",
            slug="inactive-phone",
            sku="INACTIVE-PHONE",
            price=Decimal("100000"),
            stock=5,
            is_active=False,
        )
        Product.objects.create(
            seller=self.seller,
            category=self.phones,
            name="Out of stock phone",
            slug="out-of-stock-phone",
            sku="OUT-OF-STOCK-PHONE",
            price=Decimal("100000"),
            stock=0,
        )

        response = self.client.get(
            reverse("apps:category", kwargs={"slug": self.phones.slug})
        )

        self.assertEqual(response.context["product_count"], 1)
        self.assertNotContains(response, "Inactive phone")
        self.assertNotContains(response, "Out of stock phone")

    def test_product_and_seller_have_precise_dynamic_urls(self):
        product_response = self.client.get(
            reverse("apps:product", kwargs={"slug": self.discount_product.slug})
        )
        seller_response = self.client.get(
            reverse("apps:seller", kwargs={"pk": self.seller.pk})
        )

        self.assertEqual(product_response.status_code, 200)
        self.assertContains(product_response, self.discount_product.name)
        self.assertContains(product_response, self.seller.store_name)
        self.assertEqual(seller_response.status_code, 200)
        self.assertContains(seller_response, self.discount_product.name)

    def test_unknown_or_inactive_detail_objects_return_404(self):
        self.seller.is_active = False
        self.seller.save(update_fields=("is_active",))

        self.assertEqual(self.client.get("/category/unknown/").status_code, 404)
        self.assertEqual(self.client.get("/product/unknown/").status_code, 404)
        self.assertEqual(
            self.client.get(reverse("apps:seller", kwargs={"pk": self.seller.pk})).status_code,
            404,
        )

    def test_legacy_demo_urls_redirect_to_precise_urls(self):
        self.assertRedirects(
            self.client.get(reverse("apps:category-legacy")),
            reverse("apps:category", kwargs={"slug": "audio"}),
        )
        self.assertRedirects(
            self.client.get(reverse("apps:product-legacy")),
            reverse("apps:product", kwargs={"slug": self.best_seller.slug}),
        )
        self.assertRedirects(
            self.client.get(reverse("apps:seller-legacy")),
            reverse("apps:seller", kwargs={"pk": self.seller.pk}),
        )

    def test_category_filters_by_brand_price_discount_and_rating(self):
        response = self.client.get(
            reverse("apps:category", kwargs={"slug": self.electronics.slug}),
            {
                "brand": "samsung",
                "min_price": "700000",
                "max_price": "900000",
                "discount": "1",
                "rating": "4",
            },
        )

        self.assertEqual(response.context["product_count"], 1)
        self.assertContains(response, self.discount_product.name)
        self.assertNotContains(response, self.best_seller.name)
        self.assertEqual(response.context["filter_state"]["brand"], "samsung")
        self.assertEqual(response.context["filter_state"]["rating"], 4)

    def test_availability_filter_can_show_out_of_stock_products(self):
        unavailable = Product.objects.create(
            seller=self.seller,
            category=self.phones,
            name="Unavailable Galaxy",
            slug="unavailable-galaxy",
            sku="UNAVAILABLE-GALAXY",
            price=Decimal("500000"),
            stock=0,
        )

        default_response = self.client.get(reverse("apps:search"), {"q": "Galaxy"})
        unavailable_response = self.client.get(
            reverse("apps:search"),
            {"q": "Galaxy", "availability": "out_of_stock"},
        )

        self.assertNotContains(default_response, unavailable.name)
        self.assertContains(unavailable_response, unavailable.name)
        self.assertNotContains(unavailable_response, self.discount_product.name)

    def test_sorting_supports_popular_price_rating_and_newest(self):
        url = reverse("apps:category", kwargs={"slug": self.electronics.slug})

        popular = self.client.get(url, {"sort": "popular"})
        cheapest = self.client.get(url, {"sort": "price_asc"})
        expensive = self.client.get(url, {"sort": "price_desc"})
        rating = self.client.get(url, {"sort": "rating"})
        newest = self.client.get(url, {"sort": "newest"})

        self.assertEqual(popular.context["products"][0], self.best_seller)
        self.assertEqual(cheapest.context["products"][0], self.discount_product)
        self.assertEqual(expensive.context["products"][0], self.best_seller)
        self.assertEqual(rating.context["products"][0], self.discount_product)
        self.assertEqual(newest.context["products"][0], self.best_seller)

    def test_category_and_search_pagination_preserve_filter_query(self):
        Product.objects.bulk_create([
            Product(
                seller=self.seller,
                category=self.phones,
                name=f"Page item {index:02d}",
                slug=f"page-item-{index:02d}",
                sku=f"PAGE-ITEM-{index:02d}",
                price=Decimal("750000") + index,
                stock=5,
            )
            for index in range(13)
        ])
        category_url = reverse("apps:category", kwargs={"slug": self.phones.slug})
        category_response = self.client.get(
            category_url,
            {"min_price": "700000", "sort": "price_asc", "page": "2"},
        )
        search_response = self.client.get(
            reverse("apps:search"),
            {"q": "Page item", "availability": "all", "sort": "newest", "page": "2"},
        )

        self.assertEqual(category_response.context["page_obj"].number, 2)
        self.assertIn("min_price=700000", category_response.context["filter_query"])
        self.assertIn("sort=price_asc", category_response.context["filter_query"])
        self.assertNotIn("page=", category_response.context["filter_query"])
        self.assertEqual(search_response.context["page_obj"].number, 2)
        self.assertIn("q=Page+item", search_response.context["filter_query"])
        self.assertIn("availability=all", search_response.context["filter_query"])

    def test_out_of_stock_product_is_accessible_and_marked_unavailable(self):
        product = Product.objects.create(
            seller=self.seller,
            category=self.phones,
            name="Out of stock vision",
            slug="out-of-stock-vision",
            sku="OUT-OF-STOCK-VISION",
            price=Decimal("740000"),
            stock=0,
        )

        response = self.client.get(reverse("apps:product", kwargs={"slug": product.slug}))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["is_out_of_stock"])
        self.assertEqual(response.context["display_stock"], 0)

    def test_seller_slug_route_uses_store_slug_when_available(self):
        slug = slugify(self.seller.store_name)
        response = self.client.get(reverse("apps:seller_slug", kwargs={"pk_or_slug": slug}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["seller"], self.seller)

    def test_product_variant_updates_detail_price_and_stock_context(self):
        product = Product.objects.create(
            seller=self.seller,
            category=self.phones,
            name="Variant phone",
            slug="variant-phone",
            sku="VARIANT-PHONE",
            price=Decimal("900000"),
            stock=0,
        )
        variant = ProductVariant.objects.create(
            product=product,
            name="8/256 GB",
            sku="VARIANT-PHONE-8256",
            extra_price=Decimal("50000"),
            stock=7,
        )

        response = self.client.get(reverse("apps:product", kwargs={"slug": product.slug}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_variant"], variant)
        self.assertEqual(response.context["display_price"], Decimal("950000"))
        self.assertEqual(response.context["display_stock"], 7)
        self.assertFalse(response.context["is_out_of_stock"])
        self.assertContains(response, 'data-variant-id="{}"'.format(variant.pk))

    def test_seller_products_are_paginated(self):
        Product.objects.bulk_create([
            Product(
                seller=self.seller,
                category=self.phones,
                name=f"Seller page item {index:02d}",
                slug=f"seller-page-item-{index:02d}",
                sku=f"SELLER-PAGE-{index:02d}",
                price=Decimal("100000") + index,
                stock=1,
            )
            for index in range(13)
        ])

        response = self.client.get(
            reverse("apps:seller", kwargs={"pk": self.seller.pk}),
            {"page": "2"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_obj"].number, 2)
        self.assertEqual(response.context["product_count"], 15)
        self.assertNotIn("page=", response.context["filter_query"])


class WishlistAndCompareTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.customer = User.objects.create_user(
            email="customer@example.com",
            username="customer",
            password="StrongPass2026!",
        )
        seller_user = User.objects.create_user(
            email="seller@example.com",
            username="seller",
            password="StrongPass2026!",
            role=User.Role.SELLER,
        )
        cls.seller = Seller.objects.create(user=seller_user, store_name="Test Store")
        cls.category = Category.objects.create(name="Test Category", slug="test-category")
        cls.product1 = Product.objects.create(
            seller=cls.seller,
            category=cls.category,
            name="Product 1",
            slug="product-1",
            sku="PROD-1",
            price=Decimal("100000"),
            stock=10,
        )
        cls.product2 = Product.objects.create(
            seller=cls.seller,
            category=cls.category,
            name="Product 2",
            slug="product-2",
            sku="PROD-2",
            price=Decimal("200000"),
            stock=10,
        )

    def test_wishlist_toggle_requires_authentication(self):
        response = self.client.post(
            reverse("apps:wishlist-toggle", kwargs={"product_id": self.product1.pk})
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_wishlist_ajax_guest_gets_safe_login_url(self):
        response = self.client.post(
            reverse("apps:wishlist-toggle", kwargs={"product_id": self.product1.pk}),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_REFERER=reverse("apps:product", kwargs={"slug": self.product1.slug}),
        )
        self.assertEqual(response.status_code, 401)
        self.assertIn(self.product1.slug, response.json()["login_url"])

    def test_wishlist_toggle_adds_and_removes_product(self):
        self.client.force_login(self.customer)

        response = self.client.post(
            reverse("apps:wishlist-toggle", kwargs={"product_id": self.product1.pk})
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertTrue(data["is_in_wishlist"])
        self.assertEqual(data["wishlist_count"], 1)
        self.assertTrue(Wishlist.objects.filter(user=self.customer, product=self.product1).exists())

        response = self.client.post(
            reverse("apps:wishlist-toggle", kwargs={"product_id": self.product1.pk})
        )
        data = response.json()
        self.assertFalse(data["is_in_wishlist"])
        self.assertEqual(data["wishlist_count"], 0)
        self.assertFalse(Wishlist.objects.filter(user=self.customer, product=self.product1).exists())

    def test_wishlist_prevents_duplicates(self):
        self.client.force_login(self.customer)
        Wishlist.objects.create(user=self.customer, product=self.product1)

        response = self.client.post(
            reverse("apps:wishlist-toggle", kwargs={"product_id": self.product1.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["is_in_wishlist"])
        self.assertEqual(Wishlist.objects.filter(user=self.customer, product=self.product1).count(), 0)

    def test_wishlist_page_shows_user_products(self):
        Wishlist.objects.create(user=self.customer, product=self.product1)
        Wishlist.objects.create(user=self.customer, product=self.product2)

        self.client.force_login(self.customer)
        response = self.client.get(reverse("apps:wishlist"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["product_count"], 2)
        self.assertContains(response, self.product1.name)
        self.assertContains(response, self.product2.name)

    def test_wishlist_page_shows_empty_state_for_anonymous(self):
        response = self.client.get(reverse("apps:wishlist"))
        self.assertRedirects(
            response,
            f"{reverse('apps:login')}?next={reverse('apps:wishlist')}",
        )

    def test_compare_add_product(self):
        response = self.client.post(
            reverse("apps:compare-add"),
            {"product_id": self.product1.pk}
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["compare_count"], 1)
        self.assertIn(str(self.product1.category_id), self.client.session.get("compare_items", {}))

    def test_compare_does_not_duplicate_product(self):
        self.client.post(reverse("apps:compare-add"), {"product_id": self.product1.pk})
        response = self.client.post(
            reverse("apps:compare-add"), {"product_id": self.product1.pk}
        )
        self.assertEqual(response.json()["compare_count"], 1)
        self.assertEqual(
            self.client.session["compare_items"][str(self.product1.category_id)],
            [str(self.product1.pk)],
        )

    def test_compare_enforces_category_limit(self):
        products = [self.product1, self.product2]
        for i in range(4):
            if i < 2:
                p = products[i]
            else:
                p = Product.objects.create(
                    seller=self.seller,
                    category=self.category,
                    name=f"Product {i+1}",
                    slug=f"product-{i+1}",
                    sku=f"PROD-{i+1}",
                    price=Decimal("100000"),
                    stock=10,
                )
            self.client.post(reverse("apps:compare-add"), {"product_id": p.pk})

        product_limit = Product.objects.create(
            seller=self.seller,
            category=self.category,
            name="Product Limit",
            slug="product-limit",
            sku="PROD-LIMIT",
            price=Decimal("100000"),
            stock=10,
        )

        response = self.client.post(
            reverse("apps:compare-add"),
            {"product_id": product_limit.pk}
        )
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertIn("maksimal", data["error"])

    def test_compare_remove_product(self):
        self.client.post(reverse("apps:compare-add"), {"product_id": self.product1.pk})
        self.client.post(reverse("apps:compare-add"), {"product_id": self.product2.pk})

        response = self.client.post(
            reverse("apps:compare-remove"),
            {"product_id": self.product1.pk}
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["compare_count"], 1)

    def test_compare_clear_all(self):
        self.client.post(reverse("apps:compare-add"), {"product_id": self.product1.pk})

        response = self.client.post(reverse("apps:compare-clear"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        self.assertEqual(len(self.client.session.get("compare_items", {})), 0)

    def test_compare_page_shows_products(self):
        self.client.post(reverse("apps:compare-add"), {"product_id": self.product1.pk})
        self.client.post(reverse("apps:compare-add"), {"product_id": self.product2.pk})

        response = self.client.get(reverse("apps:compare"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["product_count"], 2)

    def test_compare_page_supports_three_products_and_comparison_fields(self):
        product3 = Product.objects.create(
            seller=self.seller,
            category=self.category,
            name="Product 3",
            slug="product-3",
            sku="PROD-3",
            description="Third product description",
            price=Decimal("300000"),
            old_price=Decimal("350000"),
            stock=7,
        )
        for product in (self.product1, self.product2, product3):
            self.client.post(reverse("apps:compare-add"), {"product_id": product.pk})

        response = self.client.get(reverse("apps:compare"))

        self.assertEqual(response.context["product_count"], 3)
        self.assertContains(response, "Kategoriya")
        self.assertContains(response, "Eski narx")
        self.assertContains(response, "Third product description")
        self.assertContains(response, product3.sku)

    def test_compare_page_shows_empty_state(self):
        response = self.client.get(reverse("apps:compare"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["product_count"], 0)
        self.assertContains(response, "Taqqoslash ro'yxati bo'sh")


class ProductCreateTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="seller-create@example.com",
            username="seller-create",
            password="StrongPass2026!",
            role=User.Role.SELLER,
        )
        self.seller = Seller.objects.create(user=self.user, store_name="Create Store")
        self.category = Category.objects.create(name="Gadjetlar", slug="gadjetlar")
        self.client.force_login(self.user)

    def test_seller_can_create_product_with_variants(self):
        response = self.client.post(reverse("apps:product-create"), {
            "name": "Test Smartfon",
            "category": self.category.pk,
            "brand": "Test Brand",
            "price": "1500000",
            "old_price": "1700000",
            "stock": "8",
            "variants": "Qora 128GB +0\nKo‘k 256GB +500000",
        })

        product = Product.objects.get(name="Test Smartfon")
        self.assertRedirects(response, reverse("apps:product", kwargs={"slug": product.slug}))
        self.assertEqual(product.seller, self.seller)
        self.assertEqual(product.brand.name, "Test Brand")
        self.assertEqual(product.variants.count(), 2)
        self.assertEqual(product.variants.get(name="Ko‘k 256GB").extra_price, Decimal("500000"))

    def test_customer_cannot_create_product(self):
        customer = User.objects.create_user(
            email="customer-create@example.com",
            username="customer-create",
            password="StrongPass2026!",
        )
        self.client.force_login(customer)
        response = self.client.get(reverse("apps:product-create"))
        self.assertEqual(response.status_code, 403)

    def test_product_form_contains_requested_categories(self):
        response = self.client.get(reverse("apps:product-create"))
        self.assertContains(response, "Smartfonlar va gadjetlar")
        self.assertContains(response, "Yuvish va tozalash vositalari")
