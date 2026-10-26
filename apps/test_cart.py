from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from .models import CartItem, Category, Product, ProductVariant, Seller, User
from .services import CartError, CartService


class CartServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="customer-cart@example.com",
            username="customer-cart",
            password="StrongPass2026!",
        )
        seller_user = User.objects.create_user(
            email="seller-cart@example.com",
            username="seller-cart",
            password="StrongPass2026!",
            role=User.Role.SELLER,
        )
        seller = Seller.objects.create(user=seller_user, store_name="Cart seller")
        category = Category.objects.create(name="Cart", slug="cart")
        self.product = Product.objects.create(
            seller=seller,
            category=category,
            name="Phone",
            slug="phone-cart",
            sku="PHONE-CART",
            price=Decimal("100.00"),
            stock=5,
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            name="Black",
            sku="PHONE-CART-BLACK",
            extra_price=Decimal("10.00"),
            stock=2,
        )

    def test_add_merges_same_product_and_snapshots_price(self):
        first = CartService.add(self.user, self.product.pk, self.variant.pk, 1)
        CartService.add(self.user, self.product.pk, self.variant.pk, 1)

        first.refresh_from_db()
        self.assertEqual(first.pk, CartItem.objects.get(pk=first.pk).pk)
        self.assertEqual(first.quantity, 2)
        self.assertEqual(first.price, Decimal("110.00"))

    def test_variant_stock_and_product_stock_are_enforced(self):
        CartService.add(self.user, self.product.pk, self.variant.pk, 2)
        with self.assertRaises(CartError):
            CartService.add(self.user, self.product.pk, self.variant.pk, 1)

    def test_update_remove_and_clear(self):
        item = CartService.add(self.user, self.product.pk, quantity=2)
        CartService.set_quantity(self.user, item.pk, 3)
        self.assertEqual(CartItem.objects.get(pk=item.pk).quantity, 3)
        CartService.remove(self.user, item.pk)
        self.assertFalse(CartItem.objects.filter(pk=item.pk).exists())
        CartService.add(self.user, self.product.pk)
        CartService.clear(self.user)
        self.assertFalse(CartItem.objects.filter(cart__user=self.user).exists())

    def test_guest_api_returns_login_url(self):
        response = self.client.post(reverse("apps:cart-add"), {"product_id": self.product.pk})
        self.assertEqual(response.status_code, 401)
        self.assertIn("login_url", response.json())
