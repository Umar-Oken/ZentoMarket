from django.contrib.auth import SESSION_KEY
from django.test import TestCase
from django.urls import reverse

from .models import Address, User


class AccountFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="account@example.com",
            username="account",
            password="password123",
            first_name="Ali",
            phone="+998901234567",
        )
        self.other_user = User.objects.create_user(
            email="other-account@example.com",
            username="other-account",
            password="password123",
        )

    def test_cabinet_pages_require_login(self):
        for name in ("account", "addresses", "orders", "wishlist", "notifications", "chat", "password-change"):
            response = self.client.get(reverse(f"apps:{name}"))
            self.assertRedirects(
                response,
                f"{reverse('apps:login')}?next={reverse(f'apps:{name}')}",
            )

    def test_profile_update_changes_only_current_user(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("apps:account"), {
            "first_name": "Vali",
            "last_name": "Karimov",
            "phone": "+998909876543",
        })
        self.assertRedirects(response, reverse("apps:account"))
        self.user.refresh_from_db()
        self.other_user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Vali")
        self.assertEqual(self.user.phone, "+998909876543")
        self.assertEqual(self.other_user.first_name, "")

    def test_account_and_header_show_authenticated_user_name_with_username_fallback(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("apps:account"))
        self.assertContains(response, "Salom, Ali 👋")
        self.assertContains(response, ">Ali<")

        self.user.first_name = ""
        self.user.last_name = ""
        self.user.save(update_fields=["first_name", "last_name"])
        response = self.client.get(reverse("apps:account"))
        self.assertContains(response, f"Salom, {self.user.username} 👋")
        self.assertContains(response, f">{self.user.username}<")

    def test_address_default_is_unique_and_foreign_address_is_not_editable(self):
        own = Address.objects.create(
            user=self.user,
            title="Uy",
            city="Toshkent",
            street="Amir Temur",
            phone="+998901234567",
            is_default=True,
        )
        foreign = Address.objects.create(
            user=self.other_user,
            title="Begona",
            city="Toshkent",
            street="Begona ko‘cha",
            phone="+998901112233",
            is_default=True,
        )
        self.client.force_login(self.user)

        response = self.client.post(reverse("apps:addresses"), {
            "action": "default",
            "address_id": foreign.pk,
        })
        self.assertEqual(response.status_code, 404)

        response = self.client.post(reverse("apps:addresses"), {
            "action": "save",
            "address_id": own.pk,
            "title": "Ish",
            "city": "Toshkent",
            "street": "Buyuk Ipak Yo‘li",
            "house_number": "10",
            "phone": "+998901234567",
            "is_default": "on",
        })
        self.assertRedirects(response, reverse("apps:addresses"))
        self.assertEqual(Address.objects.filter(user=self.user, is_default=True).count(), 1)
        self.assertTrue(Address.objects.get(pk=own.pk).is_default)
        self.assertTrue(foreign.is_default)

    def test_password_change_keeps_user_logged_in(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("apps:password-change"), {
            "old_password": "password123",
            "new_password1": "new-password123",
            "new_password2": "new-password123",
        })
        self.assertRedirects(response, reverse("apps:account"))
        self.assertEqual(int(self.client.session[SESSION_KEY]), self.user.pk)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("password123") is False)
