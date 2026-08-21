from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from personnel.models import PersonnelGroup


class UserManagementTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("admin", role=User.Role.ADMIN)
        self.sampler = User.objects.create_user("sampler", role=User.Role.SAMPLER)
        self.client.force_login(self.admin)

    def test_admin_can_create_edit_disable_and_reset_user_password(self):
        response = self.client.post(
            reverse("management:user-create"),
            {
                "username": "new_sampler",
                "role": User.Role.SAMPLER,
                "first_name": "新",
                "last_name": "人员",
                "phone": "13800138000",
                "is_active": "on",
                "password1": "SafePass123!",
                "password2": "SafePass123!",
            },
        )
        user = User.objects.get(username="new_sampler")
        self.assertRedirects(response, reverse("management:user-list"))
        self.assertTrue(user.check_password("SafePass123!"))

        response = self.client.post(
            reverse("management:user-edit", args=[user.pk]),
            {
                "username": "new_sampler",
                "role": User.Role.SAMPLER,
                "first_name": "修改",
                "last_name": "人员",
                "phone": "13900139000",
                "is_active": "on",
            },
        )
        user.refresh_from_db()
        self.assertRedirects(response, reverse("management:user-list"))
        self.assertEqual(user.first_name, "修改")

        self.assertEqual(
            self.client.get(reverse("management:user-toggle-active", args=[user.pk])).status_code,
            405,
        )
        self.client.post(reverse("management:user-toggle-active", args=[user.pk]))
        user.refresh_from_db()
        self.assertFalse(user.is_active)

        self.assertEqual(
            self.client.get(reverse("management:user-reset-password", args=[user.pk])).status_code,
            405,
        )
        response = self.client.post(
            reverse("management:user-reset-password", args=[user.pk]),
            {"password1": "NewSafePass123!", "password2": "NewSafePass123!"},
        )
        user.refresh_from_db()
        self.assertRedirects(response, reverse("management:user-list"))
        self.assertTrue(user.check_password("NewSafePass123!"))

    def test_sampler_cannot_mutate_users(self):
        self.client.force_login(self.sampler)

        response = self.client.post(reverse("management:user-toggle-active", args=[self.admin.pk]))

        self.assertEqual(response.status_code, 403)

    def test_admin_cannot_disable_current_account(self):
        response = self.client.post(reverse("management:user-toggle-active", args=[self.admin.pk]))

        self.assertRedirects(response, reverse("management:user-list"))
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_grouped_sampler_cannot_be_changed_to_admin_role(self):
        group = PersonnelGroup.objects.create(name="抽样组", created_by=self.admin)
        group.members.add(self.sampler)

        response = self.client.post(
            reverse("management:user-edit", args=[self.sampler.pk]),
            {
                "username": self.sampler.username,
                "role": User.Role.ADMIN,
                "first_name": "",
                "last_name": "",
                "phone": "",
                "is_active": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.sampler.refresh_from_db()
        self.assertEqual(self.sampler.role, User.Role.SAMPLER)
        self.assertContains(response, "请先将该用户移出所有抽样人员分组")
