from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from .models import Address, CartItem, Category, DeliveryPoint, Order, Payment, Product, Seller, SellerOrder, User
from .services import CartService


class CheckoutFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="checkout@example.com",
            username="checkout",
            password="StrongPass2026!",
            first_name="Ali",
            last_name="Valiyev",
            phone="+998901234567",
        )
        seller_user = User.objects.create_user(
            email="checkout-seller@example.com",
            username="checkout-seller",
            password="StrongPass2026!",
            role=User.Role.SELLER,
        )
        seller = Seller.objects.create(user=seller_user, store_name="Checkout seller")
        category = Category.objects.create(name="Checkout", slug="checkout")
        self.product = Product.objects.create(
            seller=seller,
            category=category,
            name="Checkout product",
            slug="checkout-product",
            sku="CHECKOUT-PRODUCT",
            price=Decimal("100000"),
            stock=5,
        )
        self.point = DeliveryPoint.objects.create(
            name="Chilonzor punkti",
            address="Chilonzor 3-kvartal",
            working_hours="09:00–21:00",
        )

    def add_to_cart(self, quantity=1):
        CartService.add(self.user, self.product.pk, quantity=quantity)
        self.client.force_login(self.user)

    def test_empty_cart_cannot_open_checkout(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("apps:checkout"))
        self.assertRedirects(response, reverse("apps:cart"))

    def test_checkout_displays_cart_subtotal_and_pickup_total(self):
        self.add_to_cart(quantity=1)
        response = self.client.get(reverse("apps:checkout"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-price="100000.00"')
        self.assertContains(response, 'data-quantity="1"')
        self.assertContains(response, 'data-subtotal="100000.00"')
        self.assertContains(response, "data-order-total")

    def test_checkout_requires_pickup_point(self):
        self.add_to_cart()
        response = self.client.post(reverse("apps:checkout"), {
            "first_name": "Ali",
            "last_name": "Valiyev",
            "phone": "+998901234567",
            "email": self.user.email,
            "delivery_type": "pickup",
            "payment_type": "card",
            "notes": "",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Topshirish punktini tanlang.")
        self.assertFalse(Order.objects.exists())

    def test_pickup_checkout_creates_order_and_clears_cart(self):
        self.add_to_cart(quantity=2)
        response = self.client.post(reverse("apps:checkout"), {
            "first_name": "Ali",
            "last_name": "Valiyev",
            "phone": "+998901234567",
            "email": self.user.email,
            "delivery_type": "pickup",
            "delivery_point": self.point.pk,
            "payment_type": "card",
            "notes": "Qo‘ng‘iroq qiling",
        })
        self.assertRedirects(response, reverse("apps:success"))
        order = Order.objects.get(user=self.user)
        self.assertEqual(order.delivery_point, self.point)
        self.assertEqual(order.delivery_fee, Decimal("0"))
        self.assertEqual(order.total, Decimal("200000"))
        self.assertEqual(order.items.get().quantity, 2)
        self.assertEqual(SellerOrder.objects.get(order=order).seller, self.product.seller)
        self.assertEqual(order.payment.provider, "demo_card")
        self.assertEqual(order.payment.status, "demo_authorized")
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 3)
        self.assertFalse(CartItem.objects.filter(cart__user=self.user).exists())

    def test_checkout_rejects_changed_stock_without_creating_order(self):
        self.add_to_cart(quantity=2)
        Product.objects.filter(pk=self.product.pk).update(stock=1)

        response = self.client.post(reverse("apps:checkout"), {
            "first_name": "Ali",
            "last_name": "Valiyev",
            "phone": "+998901234567",
            "email": self.user.email,
            "delivery_type": "pickup",
            "delivery_point": self.point.pk,
            "payment_type": "cash",
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "qoldiq yetarli emas")
        self.assertFalse(Order.objects.exists())
        self.assertFalse(Payment.objects.exists())
        self.assertEqual(CartItem.objects.get().quantity, 2)

    def test_cash_payment_has_separate_pending_status(self):
        self.add_to_cart()
        response = self.client.post(reverse("apps:checkout"), {
            "first_name": "Ali",
            "last_name": "Valiyev",
            "phone": "+998901234567",
            "email": self.user.email,
            "delivery_type": "pickup",
            "delivery_point": self.point.pk,
            "payment_type": "cash",
        })

        self.assertRedirects(response, reverse("apps:success"))
        self.assertEqual(Payment.objects.get().status, "cash_pending")

    def test_success_page_is_bound_to_created_order(self):
        self.add_to_cart()
        self.client.post(reverse("apps:checkout"), {
            "first_name": "Ali",
            "last_name": "Valiyev",
            "phone": "+998901234567",
            "email": self.user.email,
            "delivery_type": "pickup",
            "delivery_point": self.point.pk,
            "payment_type": "card",
        })
        order = Order.objects.get()

        response = self.client.get(reverse("apps:success"))

        self.assertContains(response, order.order_number)
        self.assertNotContains(response, "ZT-108248")

    def test_checkout_rejects_address_owned_by_another_user(self):
        other_user = User.objects.create_user(
            email="other@example.com",
            username="other",
            password="password123",
        )
        address = Address.objects.create(
            user=other_user,
            city="Toshkent",
            street="Begona ko‘cha",
            phone="+998901234567",
        )
        self.add_to_cart()

        response = self.client.post(reverse("apps:checkout"), {
            "first_name": "Ali",
            "last_name": "Valiyev",
            "phone": "+998901234567",
            "email": self.user.email,
            "delivery_type": "address",
            "address": address.pk,
            "payment_type": "cash",
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mavjud manzilni tanlang yoki yangi manzil kiriting.")
        self.assertFalse(Order.objects.exists())

    def test_address_checkout_requires_address_data_and_calculates_fee(self):
        self.add_to_cart()
        response = self.client.post(reverse("apps:checkout"), {
            "first_name": "Ali",
            "last_name": "Valiyev",
            "phone": "+998901234567",
            "email": self.user.email,
            "delivery_type": "address",
            "payment_type": "cash",
            "notes": "",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mavjud manzilni tanlang yoki yangi manzil kiriting.")

        response = self.client.post(reverse("apps:checkout"), {
            "first_name": "Ali",
            "last_name": "Valiyev",
            "phone": "+998901234567",
            "email": self.user.email,
            "delivery_type": "address",
            "city": "Toshkent",
            "street": "Amir Temur",
            "house_number": "108",
            "payment_type": "cash",
            "notes": "",
        })
        self.assertRedirects(response, reverse("apps:success"))
        order = Order.objects.get(user=self.user)
        self.assertEqual(order.delivery_fee, Decimal("25000"))
        self.assertEqual(order.total, Decimal("125000"))
        self.assertEqual(order.address.city, "Toshkent")

    def test_pickup_page_lists_and_filters_active_points(self):
        DeliveryPoint.objects.create(
            name="Yunusobod punkti",
            address="Yunusobod",
            is_active=True,
        )
        response = self.client.get(reverse("apps:pickup"), {"q": "Chilonzor"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.point.name)
        self.assertNotContains(response, "Yunusobod punkti")
        self.assertContains(response, f"delivery_point={self.point.pk}")

    def test_delivery_point_model_choice_uses_point_name(self):
        from .forms import CheckoutForm

        form = CheckoutForm(self.user)
        self.assertIn(
            f">{self.point.name}<",
            str(form["delivery_point"]),
        )
        self.assertNotIn("DeliveryPoint object", str(form["delivery_point"]))

    def test_pickup_selection_posts_to_session_and_checkout(self):
        self.add_to_cart()
        response = self.client.post(reverse("apps:pickup-continue"), {
            "delivery_point": self.point.pk,
        })
        self.assertRedirects(
            response,
            f"{reverse('apps:checkout')}?delivery_type=pickup&delivery_point={self.point.pk}",
        )
        self.assertEqual(self.client.session["selected_delivery_point"], self.point.pk)

    def test_pickup_selection_rejects_inactive_or_unknown_point(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("apps:pickup-continue"), {"delivery_point": 99999})
        self.assertEqual(response.status_code, 404)

    def test_checkout_uses_selected_pickup_point_from_session(self):
        self.add_to_cart()
        session = self.client.session
        session["selected_delivery_point"] = self.point.pk
        session.save()

        response = self.client.get(reverse("apps:checkout"))

        self.assertEqual(response.context["form"].initial["delivery_point"], self.point.pk)
