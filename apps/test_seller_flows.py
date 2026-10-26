from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from .models import (
    Category,
    Notification,
    Order,
    OrderItem,
    Product,
    Seller,
    SellerApplication,
    SellerOrder,
    SellerOrderStatusHistory,
    User,
)


class SellerFlowTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Elektronika", slug="electronics")
        self.customer = User.objects.create_user(
            email="customer@example.com", username="customer", password="StrongPass2026!"
        )
        self.seller_user = User.objects.create_user(
            email="seller@example.com", username="seller", password="StrongPass2026!", role=User.Role.SELLER
        )
        self.seller = Seller.objects.create(user=self.seller_user, store_name="Mening do‘konim")
        self.other_seller_user = User.objects.create_user(
            email="other-seller@example.com", username="other-seller", password="StrongPass2026!", role=User.Role.SELLER
        )
        self.other_seller = Seller.objects.create(user=self.other_seller_user, store_name="Boshqa do‘kon")
        self.product = Product.objects.create(
            seller=self.seller, category=self.category, name="Telefon", sku="PHONE-1",
            price=Decimal("1000000"), stock=5,
        )
        self.other_product = Product.objects.create(
            seller=self.other_seller, category=self.category, name="Begona telefon", sku="PHONE-2",
            price=Decimal("900000"), stock=3,
        )

    def test_customer_application_creates_notification_and_approval_creates_seller(self):
        self.client.force_login(self.customer)
        response = self.client.post(reverse("apps:sell"), {
            "full_name": "Customer Test", "phone": "+998901234567", "store_name": "Yangi market",
            "category": self.category.pk, "estimated_product_count": 12,
        })
        self.assertRedirects(response, reverse("apps:sell"))
        application = SellerApplication.objects.get(user=self.customer)
        self.assertEqual(application.status, SellerApplication.Status.PENDING)
        self.assertTrue(Notification.objects.filter(user=self.customer, notification_type="seller_application").exists())

        application.status = SellerApplication.Status.APPROVED
        application.save(update_fields=["status"])
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.role, User.Role.SELLER)
        self.assertEqual(self.customer.seller_profile.store_name, "Yangi market")
        self.assertEqual(SellerApplication.objects.filter(user=self.customer, status="pending").count(), 0)

    def test_only_one_pending_application_and_phone_validation(self):
        self.client.force_login(self.customer)
        data = {
            "full_name": "Customer Test", "phone": "+998901234567", "store_name": "Market",
            "category": self.category.pk, "estimated_product_count": 0,
        }
        self.client.post(reverse("apps:sell"), data)
        second = self.client.post(reverse("apps:sell"), data)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(SellerApplication.objects.count(), 1)
        invalid = self.client.post(reverse("apps:sell"), {**data, "phone": "90 123"})
        self.assertContains(invalid, "Telefonni")

    def test_seller_can_edit_own_store_and_product_but_not_another_sellers_product(self):
        self.client.force_login(self.seller_user)
        products_response = self.client.get(reverse("apps:seller-products"))
        self.assertContains(products_response, self.product.name)
        self.assertNotContains(products_response, self.other_product.name)

        response = self.client.post(reverse("apps:seller-dashboard"), {
            "store_name": "Yangilangan do‘kon", "description": "Yangi tavsif", "address": "Toshkent", "phone": "+998901234567",
        })
        self.assertRedirects(response, reverse("apps:seller-dashboard"))
        self.seller.refresh_from_db()
        self.assertEqual(self.seller.store_name, "Yangilangan do‘kon")

        response = self.client.post(reverse("apps:seller-product-edit", args=[self.product.pk]), {
            "name": "Telefon Pro", "category": self.category.pk, "brand": "Acme", "price": "1200000",
            "old_price": "1300000", "stock": "9", "description": "Yangilangan", "is_active": "on",
        })
        self.assertRedirects(response, reverse("apps:seller-product-edit", args=[self.product.pk]))
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 9)
        self.assertEqual(self.product.seller, self.seller)

        forbidden = self.client.get(reverse("apps:seller-product-edit", args=[self.other_product.pk]))
        self.assertEqual(forbidden.status_code, 404)
        forbidden_variant = self.client.post(reverse("apps:seller-product-variant-add", args=[self.other_product.pk]), {
            "name": "Qora", "extra_price": 0, "stock": 1, "is_active": "on",
        })
        self.assertEqual(forbidden_variant.status_code, 404)

    def test_seller_can_create_product_assigned_to_own_shop(self):
        self.client.force_login(self.seller_user)
        response = self.client.post(reverse("apps:product-create"), {
            "name": "Yangi telefon",
            "category": self.category.pk,
            "brand": "",
            "price": "250000",
            "old_price": "",
            "stock": "4",
            "description": "Yangi mahsulot",
            "is_active": "on",
            "variants": "",
        })
        self.assertEqual(response.status_code, 302)
        product = Product.objects.get(name="Yangi telefon")
        self.assertEqual(product.seller, self.seller)
        self.assertEqual(product.store, self.seller.shop_store)
        self.assertEqual(product.status, Product.Status.ACTIVE)

    def test_product_status_uses_existing_active_and_stock_fields(self):
        self.assertEqual(self.product.status, Product.Status.ACTIVE)
        self.assertEqual(self.product.status_display, "Faol")
        self.product.stock = 0
        self.product.save(update_fields=["stock"])
        self.assertEqual(self.product.status, Product.Status.OUT_OF_STOCK)
        self.product.is_active = False
        self.product.save(update_fields=["is_active"])
        self.assertEqual(self.product.status, Product.Status.INACTIVE)

    def test_seller_has_unique_shop_code_and_uses_existing_unique_user_email(self):
        self.assertRegex(self.seller.code, r"^SHOP-\d{4,}$")
        self.assertNotEqual(self.seller.code, self.other_seller.code)
        self.assertEqual(self.seller.user.email, "seller@example.com")

    def test_customer_cannot_open_seller_management(self):
        self.client.force_login(self.customer)
        for name in ("seller-dashboard", "seller-products", "seller-orders", "product-create"):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(f"apps:{name}")).status_code, 403)

    def test_seller_login_opens_its_shop_dashboard(self):
        self.seller_user.set_password("shop-login-test-password")
        self.seller_user.save(update_fields=["password"])
        response = self.client.post(reverse("apps:login"), {
            "username": self.seller_user.email,
            "password": "shop-login-test-password",
        })
        self.assertRedirects(response, reverse("apps:seller-dashboard"))

    def test_existing_seller_profile_can_login_even_if_legacy_user_role_is_customer(self):
        self.seller_user.role = User.Role.CUSTOMER
        self.seller_user.set_password("legacy-seller-password")
        self.seller_user.save(update_fields=["role", "password"])

        response = self.client.post(reverse("apps:login"), {
            "username": self.seller_user.email,
            "password": "legacy-seller-password",
        })

        self.assertRedirects(response, reverse("apps:seller-dashboard"))
        self.assertEqual(self.client.get(reverse("apps:seller-admin")).status_code, 200)
        products_response = self.client.get(reverse("apps:seller-products"))
        self.assertContains(products_response, self.product.name)
        self.assertNotContains(products_response, self.other_product.name)

        response = self.client.post(reverse("apps:seller-product-edit", args=[self.product.pk]), {
            "name": "Eski seller mahsuloti",
            "category": self.category.pk,
            "brand": "",
            "price": "1100000",
            "old_price": "",
            "stock": "6",
            "description": "",
            "is_active": "on",
        })
        self.assertRedirects(response, reverse("apps:seller-product-edit", args=[self.product.pk]))
        self.product.refresh_from_db()
        self.assertEqual(self.product.name, "Eski seller mahsuloti")

    def test_superuser_can_view_orders_from_all_shops(self):
        first_order = Order.objects.create(
            user=self.customer,
            order_number="ZT-ADMIN-SHOP-A",
            status=Order.Status.NEW,
        )
        second_order = Order.objects.create(
            user=self.customer,
            order_number="ZT-ADMIN-SHOP-B",
            status=Order.Status.NEW,
        )
        OrderItem.objects.create(
            order=first_order,
            product=self.product,
            seller=self.seller,
            product_name=self.product.name,
            price=self.product.price,
        )
        OrderItem.objects.create(
            order=second_order,
            product=self.other_product,
            seller=self.other_seller,
            product_name=self.other_product.name,
            price=self.other_product.price,
        )
        admin = User.objects.create_superuser(email="admin@example.com", password="admin-test-password")
        self.client.force_login(admin)
        self.assertEqual(self.client.get(reverse("admin:apps_user_changelist")).status_code, 200)
        response = self.client.get(reverse("admin:apps_sellerorder_changelist"))
        self.assertContains(response, first_order.order_number)
        self.assertContains(response, second_order.order_number)

    def test_seller_order_status_follows_only_allowed_steps_and_notifies_customer(self):
        order = Order.objects.create(user=self.customer, order_number="ZT-SELLER-1", status=Order.Status.NEW)
        OrderItem.objects.create(order=order, product=self.product, seller=self.seller, product_name="Telefon", price=self.product.price, quantity=1)
        self.client.force_login(self.seller_user)
        status_url = reverse("apps:seller-order-status", args=[order.order_number])
        self.client.post(status_url, {"status": Order.Status.PROCESSING})
        self.client.post(status_url, {"status": Order.Status.READY_FOR_PICKUP})
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.NEW)

        for status in (
            Order.Status.CONFIRMED,
            Order.Status.PROCESSING,
            Order.Status.SHIPPED,
            Order.Status.DELIVERED,
            Order.Status.RETURNED,
        ):
            response = self.client.post(status_url, {"status": status})
            self.assertRedirects(response, reverse("apps:seller-orders"))
        order.refresh_from_db()
        seller_order = SellerOrder.objects.get(order=order, seller=self.seller)
        self.assertEqual(seller_order.status, Order.Status.RETURNED)
        self.assertEqual(
            list(seller_order.status_history.values_list("new_status", flat=True)),
            [
                Order.Status.CONFIRMED,
                Order.Status.PROCESSING,
                Order.Status.SHIPPED,
                Order.Status.DELIVERED,
                Order.Status.RETURNED,
            ],
        )
        self.assertEqual(SellerOrderStatusHistory.objects.filter(seller_order=seller_order).count(), 5)
        self.assertTrue(Notification.objects.filter(user=self.customer, notification_type="order").exists())

    def test_seller_can_change_own_part_of_mixed_order_but_not_foreign_shop_order(self):
        mixed = Order.objects.create(user=self.customer, order_number="ZT-MIXED", status=Order.Status.NEW)
        OrderItem.objects.create(order=mixed, product=self.product, seller=self.seller, product_name="Telefon", price=self.product.price, quantity=1)
        OrderItem.objects.create(order=mixed, product=self.other_product, seller=self.other_seller, product_name="Boshqa", price=self.other_product.price, quantity=1)
        foreign = Order.objects.create(user=self.customer, order_number="ZT-FOREIGN", status=Order.Status.NEW)
        OrderItem.objects.create(order=foreign, product=self.other_product, seller=self.other_seller, product_name="Boshqa", price=self.other_product.price, quantity=1)
        self.client.force_login(self.seller_user)
        response = self.client.get(reverse("apps:seller-orders"))
        self.assertContains(response, mixed.order_number)
        self.assertNotContains(response, foreign.order_number)
        self.assertContains(response, "Telefon")
        self.assertNotContains(response, "Boshqa")
        own_detail = self.client.get(reverse("apps:seller-order-detail", args=[mixed.order_number]))
        self.assertEqual(own_detail.status_code, 200)
        self.assertContains(own_detail, "Telefon")
        self.assertNotContains(own_detail, "Boshqa")
        foreign_detail = self.client.get(reverse("apps:seller-order-detail", args=[foreign.order_number]))
        self.assertEqual(foreign_detail.status_code, 404)

        self.client.post(
            reverse("apps:seller-order-status", args=[mixed.order_number]),
            {"status": Order.Status.CONFIRMED},
        )
        self.client.post(
            reverse("apps:seller-order-status", args=[foreign.order_number]),
            {"status": Order.Status.CONFIRMED},
        )
        mixed.refresh_from_db()
        foreign.refresh_from_db()
        self.assertEqual(SellerOrder.objects.get(order=mixed, seller=self.seller).status, Order.Status.CONFIRMED)
        self.assertEqual(SellerOrder.objects.get(order=mixed, seller=self.other_seller).status, Order.Status.NEW)
        self.assertEqual(foreign.status, Order.Status.NEW)
        self.assertFalse(SellerOrder.objects.filter(order=foreign, seller=self.seller).exists())

    def test_foreign_product_post_edits_and_deletes_are_blocked(self):
        self.client.force_login(self.seller_user)
        edit_url = reverse("apps:seller-product-edit", args=[self.other_product.pk])
        response = self.client.post(edit_url, {
            "name": "Ruxsatsiz tahrir",
            "category": self.category.pk,
            "brand": "",
            "price": "1",
            "old_price": "",
            "stock": "99",
            "description": "",
            "is_active": "on",
        })
        self.assertEqual(response.status_code, 404)

        delete_url = reverse("apps:seller-product-delete", args=[self.other_product.pk])
        self.assertEqual(self.client.post(delete_url).status_code, 404)
        self.other_product.refresh_from_db()
        self.assertEqual(self.other_product.name, "Begona telefon")
        self.assertEqual(self.other_product.stock, 3)

    def test_seller_can_delete_own_product_unless_order_history_protects_it(self):
        self.client.force_login(self.seller_user)
        delete_url = reverse("apps:seller-product-delete", args=[self.product.pk])
        response = self.client.post(delete_url)
        self.assertRedirects(response, reverse("apps:seller-products"))
        self.assertFalse(Product.objects.filter(pk=self.product.pk).exists())

        protected_product = Product.objects.create(
            seller=self.seller,
            category=self.category,
            name="Xarid qilingan mahsulot",
            sku="PHONE-PROTECTED",
            price=Decimal("100000"),
        )
        order = Order.objects.create(user=self.customer, order_number="ZT-PROTECTED-DELETE")
        OrderItem.objects.create(
            order=order,
            product=protected_product,
            seller=self.seller,
            product_name=protected_product.name,
            price=protected_product.price,
        )
        response = self.client.post(reverse("apps:seller-product-delete", args=[protected_product.pk]))
        self.assertRedirects(response, reverse("apps:seller-products"))
        self.assertTrue(Product.objects.filter(pk=protected_product.pk).exists())

    def test_pickup_status_and_history_are_visible_to_customer(self):
        order = Order.objects.create(
            user=self.customer,
            order_number="ZT-PICKUP-STATUS",
            delivery_type=Order.DeliveryType.PICKUP,
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            seller=self.seller,
            product_name=self.product.name,
            price=self.product.price,
        )
        self.client.force_login(self.seller_user)
        status_url = reverse("apps:seller-order-status", args=[order.order_number])
        for status in (
            Order.Status.CONFIRMED,
            Order.Status.PROCESSING,
            Order.Status.SHIPPED,
            Order.Status.READY_FOR_PICKUP,
            Order.Status.DELIVERED,
        ):
            self.client.post(status_url, {"status": status})

        seller_order = SellerOrder.objects.get(order=order, seller=self.seller)
        history = list(seller_order.status_history.all())
        self.assertEqual(history[-2].new_status, Order.Status.READY_FOR_PICKUP)
        self.assertEqual(history[-2].changed_by, self.seller_user)
        self.assertIsNotNone(history[-2].changed_at)
        self.assertEqual(history[-1].new_status, Order.Status.DELIVERED)

        self.client.force_login(self.customer)
        response = self.client.get(reverse("apps:order-detail", args=[order.order_number]))
        self.assertContains(response, Order.Status.READY_FOR_PICKUP.label)
        self.assertContains(response, Order.Status.DELIVERED.label)
        self.assertTrue(Notification.objects.filter(user=self.customer, notification_type="order").exists())

    def test_shop_cancellation_restores_only_its_stock_and_customer_cancel_does_not_restore_twice(self):
        order = Order.objects.create(user=self.customer, order_number="ZT-CANCEL-MIXED", status=Order.Status.NEW)
        OrderItem.objects.create(order=order, product=self.product, seller=self.seller, product_name="Telefon", price=self.product.price, quantity=1)
        OrderItem.objects.create(order=order, product=self.other_product, seller=self.other_seller, product_name="Boshqa", price=self.other_product.price, quantity=1)
        self.client.force_login(self.seller_user)
        self.client.post(
            reverse("apps:seller-order-status", args=[order.order_number]),
            {"status": Order.Status.CANCELLED},
        )
        self.product.refresh_from_db()
        self.other_product.refresh_from_db()
        self.assertEqual(self.product.stock, 6)
        self.assertEqual(self.other_product.stock, 3)

        self.client.force_login(self.customer)
        response = self.client.post(reverse("apps:order-cancel", args=[order.order_number]))
        self.assertRedirects(response, reverse("apps:order-detail", args=[order.order_number]))
        self.product.refresh_from_db()
        self.other_product.refresh_from_db()
        self.assertEqual(self.product.stock, 6)
        self.assertEqual(self.other_product.stock, 4)
        self.assertEqual(
            SellerOrder.objects.get(order=order, seller=self.seller).status,
            Order.Status.CANCELLED,
        )
        self.assertEqual(
            SellerOrder.objects.get(order=order, seller=self.other_seller).status,
            Order.Status.CANCELLED,
        )

    def test_public_seller_uses_review_rating_and_catalog_filter(self):
        response = self.client.get(reverse("apps:seller", args=[self.seller.pk]), {"min_price": "1100000"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["product_count"], 0)
        self.assertContains(response, "Mahsulotlar reytingi")
