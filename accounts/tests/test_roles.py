from django.test import TestCase
from django.urls import reverse

from accounts.models import User


class RoleGateTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            "admin", password="Pass12345!", role=User.Role.ADMIN
        )
        self.sampler = User.objects.create_user(
            "sampler", password="Pass12345!", role=User.Role.SAMPLER
        )

    def test_admin_login_redirects_to_management(self):
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "admin", "password": "Pass12345!"},
        )

        self.assertRedirects(response, "/manage/")

    def test_sampler_login_redirects_to_mobile(self):
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "sampler", "password": "Pass12345!"},
        )

        self.assertRedirects(response, "/m/")

    def test_sampler_cannot_open_management(self):
        self.client.force_login(self.sampler)

        self.assertEqual(self.client.get("/manage/").status_code, 403)

    def test_admin_cannot_open_mobile(self):
        self.client.force_login(self.admin)

        self.assertEqual(self.client.get("/m/").status_code, 403)

    def test_anonymous_profile_request_redirects_to_login(self):
        response = self.client.get(reverse("accounts:profile"))

        self.assertRedirects(response, reverse("accounts:login"))
