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

    def test_login_remember_me_controls_session_expiry(self):
        login_url = reverse("accounts:login")
        credentials = {"username": "admin", "password": "Pass12345!"}

        self.client.post(login_url, credentials)
        self.assertTrue(self.client.session.get_expire_at_browser_close())

        self.client.post(reverse("accounts:logout"))
        self.client.post(login_url, {**credentials, "remember_me": "on"})
        self.assertFalse(self.client.session.get_expire_at_browser_close())

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

    def test_admin_cannot_open_sampler_profile(self):
        self.client.force_login(self.admin)

        self.assertEqual(self.client.get(reverse("accounts:profile")).status_code, 403)

    def test_sampler_profile_post_persists_only_allowlisted_fields(self):
        self.client.force_login(self.sampler)

        response = self.client.post(
            reverse("accounts:profile"),
            {
                "action": "update_profile",
                "first_name": "抽样",
                "avatar_choice": "icon3",
                "last_name": "人员",
                "phone": "13800138000",
                "username": "changed-admin",
                "role": User.Role.ADMIN,
            },
        )

        self.assertRedirects(response, reverse("accounts:profile"))
        self.sampler.refresh_from_db()
        self.assertEqual(self.sampler.first_name, "抽样")
        self.assertEqual(self.sampler.avatar_choice, "icon3")
        self.assertEqual(self.sampler.last_name, "")
        self.assertEqual(self.sampler.phone, "")
        self.assertEqual(self.sampler.username, "sampler")
        self.assertEqual(self.sampler.role, User.Role.SAMPLER)

    def test_unknown_authenticated_role_is_denied_login_routing(self):
        unknown_role_user = User.objects.create_user(
            "unknown", password="Pass12345!", role="unexpected"
        )
        self.client.force_login(unknown_role_user)

        self.assertEqual(self.client.get(reverse("accounts:login")).status_code, 403)

    def test_logout_is_post_only_and_ends_the_session(self):
        self.client.force_login(self.sampler)

        self.assertEqual(self.client.get(reverse("accounts:logout")).status_code, 405)
        response = self.client.post(reverse("accounts:logout"))
        self.assertRedirects(response, reverse("accounts:login"))
        self.assertRedirects(self.client.get("/m/"), reverse("accounts:login"))
