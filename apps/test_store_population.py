from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from .models import Category, Product, Seller, Store, User
from .store_emails import store_email_for_seller


class PopulateStoreDataTests(TestCase):
    def setUp(self):
        self.seller_user = User.objects.create_user(
            email="store-owner@example.com",
            password="SafeStoreOwnerPassword2026!",
            role=User.Role.SELLER,
        )
        self.seller = Seller.objects.create(user=self.seller_user, store_name="Verified Auto")
        self.category = Category.objects.create(name="Store command category", slug="store-command-category")

    def test_command_uses_product_seller_and_is_idempotent(self):
        store = Store.objects.create(name="Seller product store", slug="seller-product-store")
        Product.objects.create(
            seller=self.seller,
            store=store,
            category=self.category,
            name="Seller-owned product",
            slug="seller-owned-product",
            sku="SELLER-OWNED-PRODUCT",
            price=Decimal("100000"),
        )

        call_command("populate_store_data", stdout=StringIO())
        store.refresh_from_db()
        self.assertEqual(store.seller_id, self.seller.pk)
        self.assertEqual(store.email, store_email_for_seller(self.seller, store))
        self.assertEqual(store.shop_code, f"SHOP-{store.pk:04d}")
        original_values = (store.email, store.seller_id, store.shop_code, store.updated_at)

        call_command("populate_store_data", stdout=StringIO())
        store.refresh_from_db()
        self.assertEqual(
            (store.email, store.seller_id, store.shop_code, store.updated_at),
            original_values,
        )

    def test_each_store_gets_a_distinct_email_alias_and_tracks_account_email(self):
        first = self.seller.shop_store
        second = Store.objects.create(
            name="Second verified store",
            slug="second-verified-store",
            seller=self.seller,
            shop_code="SHOP-SECOND",
            email=self.seller_user.email,
        )

        call_command("populate_store_data", stdout=StringIO())
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertNotEqual(first.email, second.email)
        self.assertEqual(first.email, self.seller_user.email)
        self.assertEqual(second.email, "store-owner+shop-second@example.com")

        self.seller_user.email = "updated-owner@example.com"
        self.seller_user.save(update_fields=["email"])
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.email, "updated-owner@example.com")
        self.assertEqual(second.email, "updated-owner+shop-second@example.com")

    def test_command_does_not_guess_for_unlinked_store_and_validates_remaining_null(self):
        store = Store.objects.create(name="Unlinked catalog", slug="unlinked-catalog")
        with self.assertRaises(CommandError):
            call_command("populate_store_data", stdout=StringIO(), stderr=StringIO())
        store.refresh_from_db()
        self.assertIsNone(store.seller_id)
        self.assertEqual(store.email, "")
        self.assertTrue(store.shop_code)

        output = StringIO()
        call_command(
            "populate_store_data",
            f"--map-store={store.pk}={self.seller.pk}",
            stdout=output,
        )
        store.refresh_from_db()
        self.assertEqual(store.seller_id, self.seller.pk)
        self.assertEqual(store.email, store_email_for_seller(self.seller, store))
        self.assertIn("Barcha Store qatorlari", output.getvalue())

    def test_command_does_not_assign_store_with_products_from_multiple_sellers(self):
        other_user = User.objects.create_user(
            email="other-store-owner@example.com",
            password="SafeOtherOwnerPassword2026!",
            role=User.Role.SELLER,
        )
        other_seller = Seller.objects.create(user=other_user, store_name="Other verified store")
        store = Store.objects.create(name="Mixed catalog store", slug="mixed-catalog-store")
        for index, seller in enumerate((self.seller, other_seller), start=1):
            Product.objects.create(
                seller=seller,
                store=store,
                category=self.category,
                name=f"Mixed product {index}",
                slug=f"mixed-product-{index}",
                sku=f"MIXED-STORE-{index}",
                price=Decimal("100000"),
            )

        with self.assertRaises(CommandError):
            call_command("populate_store_data", stdout=StringIO(), stderr=StringIO())
        store.refresh_from_db()
        self.assertIsNone(store.seller_id)
        self.assertEqual(store.email, "")
        self.assertTrue(store.shop_code)

        with self.assertRaises(CommandError):
            call_command(
                "populate_store_data",
                f"--map-store={store.pk}={self.seller.pk}",
                stdout=StringIO(),
                stderr=StringIO(),
            )
        store.refresh_from_db()
        self.assertIsNone(store.seller_id)
