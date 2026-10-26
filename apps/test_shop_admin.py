from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from .models import Category, Order, OrderItem, Product, Seller, SellerOrder, Store, User


class MultiVendorAdminTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Shop admin category", slug="shop-admin-category")
        self.customer = User.objects.create_user(
            email="shop-customer@example.com",
            password="SafeCustomerPassword2026!",
        )
        self.superuser = User.objects.create_superuser(
            email="global-admin@example.com",
            password="SafeGlobalPassword2026!",
        )
        self.seller_user = User.objects.create_user(
            email="seller-a@example.com",
            password="SafeSellerPassword2026!",
            role=User.Role.SELLER,
        )
        self.seller = Seller.objects.create(user=self.seller_user, store_name="Shop A")
        self.shop = self.seller.shop_store
        self.other_user = User.objects.create_user(
            email="seller-b@example.com",
            password="SafeOtherPassword2026!",
            role=User.Role.SELLER,
        )
        self.other_seller = Seller.objects.create(user=self.other_user, store_name="Shop B")
        self.product = Product.objects.create(
            seller=self.seller,
            store=self.shop,
            category=self.category,
            name="Shop A product",
            slug="shop-a-product",
            sku="SHOP-A-PRODUCT",
            price=Decimal("125000"),
            stock=4,
        )
        self.other_product = Product.objects.create(
            seller=self.other_seller,
            store=self.other_seller.shop_store,
            category=self.category,
            name="Shop B product",
            slug="shop-b-product",
            sku="SHOP-B-PRODUCT",
            price=Decimal("89000"),
            stock=2,
        )

    def test_existing_seller_is_provisioned_with_private_shop_and_group(self):
        catalog_store = Store.objects.create(name="Legacy catalog store", slug="legacy-catalog-store")
        self.assertIsNone(catalog_store.seller_id)
        self.assertFalse(Seller.objects.filter(shop_stores__isnull=True).exists())
        self.assertTrue(self.shop.shop_code.startswith("SHOP-"))
        self.assertEqual(self.shop.email, self.seller_user.email)
        self.assertTrue(self.shop.is_active)
        self.assertNotEqual(self.shop.shop_code, self.other_seller.shop_store.shop_code)
        self.assertTrue(self.seller_user.groups.filter(name="ShopAdmin").exists())
        self.assertTrue(self.seller_user.has_perm("apps.manage_shop_dashboard"))
        self.assertTrue(self.seller_user.has_perm("apps.change_product"))
        self.assertTrue(self.superuser.groups.filter(name="SuperAdmin").exists())

    def test_global_dashboard_is_superuser_only_and_shows_global_counts(self):
        response = self.client.get(reverse("apps:super-admin"))
        self.assertRedirects(
            response,
            f"{reverse('apps:login')}?next={reverse('apps:super-admin')}",
        )

        self.client.force_login(self.seller_user)
        self.assertEqual(self.client.get(reverse("apps:super-admin")).status_code, 403)

        self.client.force_login(self.superuser)
        response = self.client.get(reverse("apps:super-admin"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "seller-a@example.com")
        self.assertContains(response, self.shop.shop_code)
        self.assertEqual(response.context["shop_count"], Seller.objects.count())
        self.assertEqual(response.context["product_count"], Product.objects.count())

    def test_superadmin_can_create_shop_with_hashed_password_and_unique_code(self):
        self.client.force_login(self.superuser)
        response = self.client.post(reverse("apps:super-admin-shop-create"), {
            "store_name": "Zento Auto",
            "description": "Avtomobil ehtiyot qismlari",
            "email": "zentoauto@gmail.com",
            "phone": "+998901234567",
            "password": "ZentoAuto!Password2026",
        })

        self.assertRedirects(response, reverse("apps:super-admin"))
        shop = Store.objects.get(name="Zento Auto")
        shop_admin = shop.seller.user
        self.assertEqual(shop.email, "zentoauto@gmail.com")
        self.assertTrue(shop.shop_code)
        self.assertFalse(shop_admin.password == "ZentoAuto!Password2026")
        self.assertTrue(shop_admin.check_password("ZentoAuto!Password2026"))
        self.assertTrue(shop_admin.groups.filter(name="ShopAdmin").exists())
        self.assertEqual(shop_admin.role, User.Role.SELLER)

    def test_superadmin_can_edit_shop_and_admin_account_and_toggle_active(self):
        self.client.force_login(self.superuser)
        edit_url = reverse("apps:super-admin-shop-edit", args=[self.shop.pk])
        response = self.client.post(edit_url, {
            "store_name": "Shop A Updated",
            "description": "Updated description",
            "admin_email": "seller-a-updated@example.com",
            "phone": "+998901234567",
            "store_is_active": "on",
            "admin_is_active": "on",
            "new_password": "UpdatedSeller!Password2026",
        })
        self.assertRedirects(response, reverse("apps:super-admin"))
        self.shop.refresh_from_db()
        self.seller_user.refresh_from_db()
        self.assertEqual(self.shop.name, "Shop A Updated")
        self.assertEqual(self.shop.email, self.seller_user.email)
        self.assertEqual(self.seller_user.email, "seller-a-updated@example.com")
        self.assertTrue(self.seller_user.check_password("UpdatedSeller!Password2026"))

        toggle_url = reverse("apps:super-admin-shop-toggle", args=[self.shop.pk])
        self.client.post(toggle_url)
        self.shop.refresh_from_db()
        self.seller.refresh_from_db()
        self.assertFalse(self.shop.is_active)
        self.assertFalse(self.seller.is_active)
        self.assertEqual(self.client.get(reverse("apps:seller-dashboard")).status_code, 403)

        self.client.post(toggle_url)
        self.shop.refresh_from_db()
        self.seller.refresh_from_db()
        self.assertTrue(self.shop.is_active)
        self.assertTrue(self.seller.is_active)

    def test_shop_customers_and_dashboard_sales_are_scoped_to_its_seller_order(self):
        order = Order.objects.create(
            user=self.customer,
            order_number="ZT-SHOP-REVENUE",
            status=Order.Status.NEW,
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            seller=self.seller,
            product_name=self.product.name,
            price=self.product.price,
            quantity=2,
        )
        other_customer = User.objects.create_user(
            email="other-customer@example.com",
            password="SafeCustomerPassword2026!",
        )
        other_order = Order.objects.create(user=other_customer, order_number="ZT-OTHER-REVENUE")
        OrderItem.objects.create(
            order=other_order,
            product=self.other_product,
            seller=self.other_seller,
            product_name=self.other_product.name,
            price=self.other_product.price,
        )

        self.client.force_login(self.seller_user)
        dashboard = self.client.get(reverse("apps:seller-dashboard"))
        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(dashboard.context["today_sales"], Decimal("250000"))
        self.assertEqual(dashboard.context["monthly_sales"], Decimal("250000"))
        self.assertEqual(dashboard.context["customer_count"], 1)

        customers = self.client.get(reverse("apps:seller-customers"))
        self.assertContains(customers, self.customer.email)
        self.assertNotContains(customers, other_customer.email)
        self.assertEqual(customers.context["customer_count"], 1)

    def test_shop_deletion_preserves_catalog_and_order_history(self):
        self.client.force_login(self.superuser)
        empty_seller = Seller.objects.create(
            user=User.objects.create_user(
                email="empty-shop@example.com",
                password="SafeEmptyPassword2026!",
                role=User.Role.SELLER,
            ),
            store_name="Empty shop",
        )
        empty_shop_id = empty_seller.shop_store.pk
        empty_user_id = empty_seller.user_id
        response = self.client.post(reverse("apps:super-admin-shop-delete", args=[empty_shop_id]))
        self.assertRedirects(response, reverse("apps:super-admin"))
        self.assertFalse(Store.objects.filter(pk=empty_shop_id).exists())
        self.assertFalse(User.objects.get(pk=empty_user_id).is_active)

        protected_shop_id = self.shop.pk
        order = Order.objects.create(user=self.customer, order_number="ZT-SHOP-DELETE-PROTECTED")
        order_item = OrderItem.objects.create(
            order=order,
            product=self.product,
            seller=self.seller,
            product_name=self.product.name,
            price=self.product.price,
        )
        response = self.client.post(reverse("apps:super-admin-shop-delete", args=[protected_shop_id]))
        self.assertRedirects(response, reverse("apps:super-admin"))
        self.assertFalse(Store.objects.filter(pk=protected_shop_id).exists())
        self.assertTrue(Seller.objects.filter(pk=self.seller.pk).exists())
        self.assertFalse(User.objects.get(pk=self.seller_user.pk).is_active)
        self.product.refresh_from_db()
        self.assertIsNone(self.product.store_id)
        order_item.refresh_from_db()
        self.assertEqual(order_item.product_id, self.product.pk)

    def test_seller_cannot_manage_other_shop_or_enter_django_admin(self):
        self.client.force_login(self.seller_user)
        response = self.client.get(reverse("apps:seller-products"))
        self.assertContains(response, self.product.name)
        self.assertNotContains(response, self.other_product.name)
        self.assertEqual(
            self.client.get(reverse("apps:seller-product-edit", args=[self.other_product.pk])).status_code,
            404,
        )
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 302)

        self.seller_user.is_staff = True
        self.seller_user.save(update_fields=["is_staff"])
        self.client.force_login(self.seller_user)
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 302)

    def test_superadmin_can_create_users_from_django_admin_with_hashed_password(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("admin:apps_user_add"))
        self.assertEqual(response.status_code, 200)
        response = self.client.post(reverse("admin:apps_user_add"), {
            "email": "created-user@example.com",
            "first_name": "Created",
            "last_name": "User",
            "phone": "+998901234567",
            "role": User.Role.CUSTOMER,
            "is_active": "on",
            "is_staff": "",
            "is_superuser": "",
            "password1": "CreatedUser!Password2026",
            "password2": "CreatedUser!Password2026",
            "_save": "Save",
        })
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(email="created-user@example.com")
        self.assertTrue(user.check_password("CreatedUser!Password2026"))
        self.assertNotEqual(user.password, "CreatedUser!Password2026")

class SellerOrderCustomerAccessTests(TestCase):
    def test_order_status_visibility_is_per_shop_for_mixed_orders(self):
        customer = User.objects.create_user(
            email="mixed-customer@example.com",
            password="SafeCustomerPassword2026!",
        )
        sellers = []
        products = []
        category = Category.objects.create(name="Mixed order category", slug="mixed-order-category")
        for index in (1, 2):
            user = User.objects.create_user(
                email=f"mixed-seller-{index}@example.com",
                password="SafeSellerPassword2026!",
                role=User.Role.SELLER,
            )
            seller = Seller.objects.create(user=user, store_name=f"Mixed Shop {index}")
            product = Product.objects.create(
                seller=seller,
                store=seller.shop_store,
                category=category,
                name=f"Mixed product {index}",
                slug=f"mixed-product-{index}",
                sku=f"MIXED-PRODUCT-{index}",
                price=Decimal("50000"),
            )
            sellers.append((user, seller))
            products.append(product)

        order = Order.objects.create(user=customer, order_number="ZT-MIXED-SELLER-CUSTOMER")
        for (user, seller), product in zip(sellers, products):
            OrderItem.objects.create(
                order=order,
                product=product,
                seller=seller,
                product_name=product.name,
                price=product.price,
            )

        self.client.force_login(sellers[0][0])
        response = self.client.get(reverse("apps:seller-orders"))
        self.assertContains(response, order.order_number)
        self.assertContains(response, products[0].name)
        self.assertNotContains(response, products[1].name)
        self.assertEqual(SellerOrder.objects.filter(order=order).count(), 2)
