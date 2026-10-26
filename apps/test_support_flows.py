from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator

from .models import (
    Category,
    Chat,
    ChatMessage,
    ContactMessage,
    Notification,
    Order,
    Product,
    ReturnRequest,
    Review,
    Seller,
)

User = get_user_model()


class NotificationChatContactSupportTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="support@example.com",
            username="support-user",
            password="password123",
            first_name="Ali",
            last_name="Vali",
            phone="+998901234567",
        )
        self.other = User.objects.create_user(
            email="seller@example.com",
            username="seller-user",
            password="password123",
            first_name="Sotuvchi",
            phone="+998909876543",
        )
        self.seller = Seller.objects.create(
            user=self.other,
            store_name="Zento Store",
            description="Test seller",
        )

    def test_notification_mark_read_and_unread_count(self):
        self.client.force_login(self.user)
        Notification.objects.create(user=self.user, title="New", message="Message")
        Notification.objects.create(user=self.user, title="Old", message="Read me", is_read=True)

        response = self.client.get(reverse("apps:notifications"))
        self.assertEqual(response.context["unread_count"], 1)
        self.assertEqual(response.context["unread_notification_count"], 1)

        notification = self.user.notifications.filter(is_read=False).first()
        response = self.client.post(
            reverse("apps:notification-read", args=[notification.pk]),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content.decode(), {"success": True, "unread_count": 0})
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)

    def test_domain_events_create_notifications_once_per_event(self):
        order = Order.objects.create(user=self.user, order_number="ZT-NOTIFY-1")
        self.assertEqual(self.user.notifications.filter(notification_type="order").count(), 1)

        order.status = Order.Status.CONFIRMED
        order.save(update_fields=["status"])
        order.total = 100_000
        order.save(update_fields=["total"])
        self.assertEqual(self.user.notifications.filter(notification_type="order").count(), 2)

        category = Category.objects.create(name="Support category")
        product = Product.objects.create(
            seller=self.seller,
            category=category,
            name="Support product",
            sku="SUPPORT-PRODUCT",
            price=100_000,
            stock=1,
        )
        Review.objects.create(user=self.user, product=product, rating=5, text="Juda yaxshi")
        return_order = Order.objects.create(user=self.user, order_number="ZT-NOTIFY-2")
        ReturnRequest.objects.create(
            user=self.user,
            order=return_order,
            reason="Mahsulot tavsifga mos kelmadi.",
        )
        self.assertEqual(self.user.notifications.filter(notification_type="review").count(), 1)
        self.assertEqual(self.user.notifications.filter(notification_type="return").count(), 1)

    def test_mark_all_notifications_read_updates_the_header_count(self):
        self.client.force_login(self.user)
        Notification.objects.create(user=self.user, title="One", message="First")
        Notification.objects.create(user=self.user, title="Two", message="Second")

        response = self.client.post(
            reverse("apps:notifications-read-all"),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertJSONEqual(response.content.decode(), {"success": True, "unread_count": 0})
        self.assertFalse(self.user.notifications.filter(is_read=False).exists())

    def test_chat_create_send_and_fetch_with_owner_checks(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("apps:chat-create"),
            {"subject": "Order help", "seller_id": self.seller.pk},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        chat = Chat.objects.get(pk=data["chat_id"])
        self.assertEqual(chat.user, self.user)
        self.assertEqual(chat.seller, self.seller)

        response = self.client.post(
            reverse("apps:chat-send"),
            {"chat_id": chat.pk, "message": "Hello there"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(chat.messages.count(), 1)

        response = self.client.get(reverse("apps:chat-messages", args=[chat.pk]), {"since": 0})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["messages"][0]["text"], "Hello there")

        other_client = self.client_class()
        other_client.force_login(self.other)
        response = other_client.post(
            reverse("apps:chat-send"),
            {"chat_id": chat.pk, "message": "Unauthorized"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 404)

    def test_chat_polling_marks_received_messages_read_and_lists_only_owned_chats(self):
        self.client.force_login(self.user)
        owned = Chat.objects.create(user=self.user, subject="My chat")
        foreign = Chat.objects.create(user=self.other, subject="Private chat")
        received = ChatMessage.objects.create(chat=owned, sender=self.other, text="Support reply")

        page = self.client.get(reverse("apps:chat"), {"chat": owned.pk})
        self.assertContains(page, "My chat")
        self.assertNotContains(page, foreign.subject)

        response = self.client.get(reverse("apps:chat-messages", args=[owned.pk]), {"since": 0})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["messages"][0]["is_mine"])
        received.refresh_from_db()
        self.assertTrue(received.is_read)

    def test_chat_create_accepts_initial_message(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("apps:chat-create"),
            {"subject": "First message", "message": "Assalomu alaykum"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        chat = Chat.objects.get(pk=response.json()["chat_id"])
        self.assertEqual(chat.messages.get().text, "Assalomu alaykum")

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_contact_form_saves_message_and_sends_email(self):
        response = self.client.post(
            reverse("apps:contact"),
            {
                "full_name": "Test User",
                "email": "user@example.com",
                "subject": "order",
                "message": "Buyurtma haqida savolim bor. Iltimos, javob bering.",
            },
        )
        self.assertRedirects(response, reverse("apps:contact"))
        self.assertEqual(ContactMessage.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("[Zento] Buyurtma bo‘yicha", mail.outbox[0].subject)
        self.assertIn("user@example.com", mail.outbox[0].body)

    def test_contact_form_rejects_short_messages_without_saving(self):
        response = self.client.post(
            reverse("apps:contact"),
            {"full_name": "Test User", "email": "user@example.com", "subject": "order", "message": "Qisqa"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "kamida 10 ta belgidan")
        self.assertFalse(ContactMessage.objects.exists())


class PasswordResetFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="reset@example.com",
            username="reset-user",
            password="password123",
        )

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_password_reset_request_and_confirm_flow(self):
        response = self.client.post(
            reverse("apps:forgot-password"),
            {"email": self.user.email},
        )
        self.assertRedirects(response, reverse("apps:password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)

        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        confirm_url = reverse("apps:password_reset_confirm", kwargs={"uidb64": uid, "token": token})

        response = self.client.get(confirm_url)
        self.assertEqual(response.status_code, 302)
        set_password_url = response.url
        self.assertTrue(set_password_url.endswith("/set-password/"))

        response = self.client.post(
            set_password_url,
            {"new_password1": "StrongPass!2025", "new_password2": "StrongPass!2025"},
        )
        self.assertRedirects(response, reverse("apps:password_reset_complete"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("StrongPass!2025"))

    def test_faq_has_keyboard_and_accordion_accessibility_state(self):
        response = self.client.get(reverse("apps:faq"))
        self.assertContains(response, 'role="toolbar"')
        self.assertContains(response, 'data-faq-toggle')
        self.assertContains(response, 'aria-expanded="true"')
