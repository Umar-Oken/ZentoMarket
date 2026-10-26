from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from .models import (
    CartItem,
    Category,
    Order,
    OrderItem,
    Payment,
    Product,
    Review,
    ReturnRequest,
    Seller,
    User,
)


class OrderWorkflowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="orders@example.com",
            username="orders",
            password="StrongPass2026!",
        )
        other_user = User.objects.create_user(
            email="other-orders@example.com",
            username="other-orders",
            password="StrongPass2026!",
        )
        seller_user = User.objects.create_user(
            email="orders-seller@example.com",
            username="orders-seller",
            password="StrongPass2026!",
            role=User.Role.SELLER,
        )
        seller = Seller.objects.create(user=seller_user, store_name="Order seller")
        category = Category.objects.create(name="Order category", slug="order-category")
        self.product = Product.objects.create(
            seller=seller,
            category=category,
            name="Order product",
            slug="order-product",
            sku="ORDER-PRODUCT",
            price=Decimal("100000"),
            stock=2,
        )
        self.order = Order.objects.create(
            user=self.user,
            order_number="ZT-ORDER-1",
            status=Order.Status.DELIVERED,
            total=Decimal("100000"),
        )
        self.item = OrderItem.objects.create(
            order=self.order,
            product=self.product,
            seller=seller,
            product_name=self.product.name,
            price=self.product.price,
            quantity=1,
        )
        Payment.objects.create(
            order=self.order,
            provider="demo_card",
            transaction_id="ORDER-PAYMENT-1",
            amount=self.order.total,
            status="demo_authorized",
        )
        self.other_order = Order.objects.create(
            user=other_user,
            order_number="ZT-ORDER-2",
            status=Order.Status.DELIVERED,
        )
        self.client.force_login(self.user)

    def test_orders_page_filters_and_paginates_owned_orders(self):
        for index in range(11):
            Order.objects.create(
                user=self.user,
                order_number=f"ZT-PAGE-{index}",
                status=Order.Status.NEW,
            )

        response = self.client.get(reverse("apps:orders"), {"status": Order.Status.NEW})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_obj"].paginator.count, 11)
        self.assertEqual(len(response.context["orders"]), 10)
        self.assertNotContains(response, self.other_order.order_number)

    def test_order_detail_is_owned_and_dynamic(self):
        response = self.client.get(
            reverse("apps:order-detail", kwargs={"order_number": self.order.order_number})
        )

        self.assertContains(response, self.order.order_number)
        self.assertContains(response, self.product.name)
        self.assertContains(response, Order.Status.DELIVERED.label)

        response = self.client.get(
            reverse("apps:order-detail", kwargs={"order_number": self.other_order.order_number})
        )
        self.assertEqual(response.status_code, 404)

    def test_cancel_allowed_status_restores_stock(self):
        self.order.status = Order.Status.NEW
        self.order.save(update_fields=["status"])
        self.order.seller_orders.update(status=Order.Status.NEW)
        self.product.stock = 0
        self.product.save(update_fields=["stock"])

        response = self.client.post(
            reverse("apps:order-cancel", kwargs={"order_number": self.order.order_number})
        )

        self.assertRedirects(
            response,
            reverse("apps:order-detail", kwargs={"order_number": self.order.order_number}),
        )
        self.order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.CANCELLED)
        self.assertEqual(self.product.stock, 1)

    def test_cancel_is_rejected_for_delivered_order(self):
        response = self.client.post(
            reverse("apps:order-cancel", kwargs={"order_number": self.order.order_number})
        )

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.DELIVERED)
        self.assertEqual(response.status_code, 302)

    def test_reorder_adds_only_available_products(self):
        self.product.stock = 1
        self.product.save(update_fields=["stock"])

        response = self.client.post(
            reverse("apps:order-reorder", kwargs={"order_number": self.order.order_number})
        )

        self.assertRedirects(response, reverse("apps:cart"))
        self.assertEqual(CartItem.objects.get().quantity, 1)

    def test_review_requires_delivery_and_prevents_duplicate(self):
        response = self.client.post(
            reverse(
                "apps:order-review",
                kwargs={"order_number": self.order.order_number, "item_id": self.item.pk},
            ),
            {"rating": 5, "text": "Juda yaxshi mahsulot."},
        )

        self.assertRedirects(
            response,
            reverse("apps:order-detail", kwargs={"order_number": self.order.order_number}),
        )
        review = Review.objects.get()
        self.assertTrue(review.is_verified_purchase)

        self.client.post(
            reverse(
                "apps:order-review",
                kwargs={"order_number": self.order.order_number, "item_id": self.item.pk},
            ),
            {"rating": 4, "text": "Yana bir sharh."},
        )
        self.assertEqual(Review.objects.count(), 1)

    def test_review_is_rejected_for_non_delivered_order(self):
        self.order.status = Order.Status.PROCESSING
        self.order.save(update_fields=["status"])

        self.client.post(
            reverse(
                "apps:order-review",
                kwargs={"order_number": self.order.order_number, "item_id": self.item.pk},
            ),
            {"rating": 5, "text": "Juda yaxshi mahsulot."},
        )

        self.assertFalse(Review.objects.exists())

    def test_return_request_is_owned_once_and_only_for_delivered_order(self):
        response = self.client.post(
            reverse("apps:order-return", kwargs={"order_number": self.order.order_number}),
            {"reason": "Mahsulot kutganimdek bo‘lmadi."},
        )

        self.assertRedirects(
            response,
            reverse("apps:order-detail", kwargs={"order_number": self.order.order_number}),
        )
        self.assertEqual(ReturnRequest.objects.count(), 1)

        self.client.post(
            reverse("apps:order-return", kwargs={"order_number": self.order.order_number}),
            {"reason": "Yana qaytarish so‘rovi."},
        )
        self.assertEqual(ReturnRequest.objects.count(), 1)

    def test_order_actions_require_order_ownership(self):
        urls = (
            reverse("apps:order-cancel", kwargs={"order_number": self.other_order.order_number}),
            reverse("apps:order-reorder", kwargs={"order_number": self.other_order.order_number}),
            reverse("apps:order-return", kwargs={"order_number": self.other_order.order_number}),
            reverse(
                "apps:order-review",
                kwargs={"order_number": self.other_order.order_number, "item_id": self.item.pk},
            ),
        )

        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.post(url).status_code, 404)
