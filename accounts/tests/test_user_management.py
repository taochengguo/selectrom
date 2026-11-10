from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from personnel.models import PersonnelGroup


class UserManagementTests(TestCase):
    def test_profile_drawer_updates_only_username_and_name(self):
        response = self.client.post(reverse("management:user-profile", args=[self.sampler.pk]), {"username": "renamed", "first_name": "王五", "role": "admin", "is_active": ""})
        self.assertEqual(response.status_code, 200)
        self.sampler.refresh_from_db()
        self.assertEqual(self.sampler.username, "renamed")
        self.assertEqual(self.sampler.first_name, "王五")
        self.assertEqual(self.sampler.role, "sampler")
        self.assertTrue(self.sampler.is_active)

    def test_profile_drawer_rejects_duplicate_username_and_sampler_access(self):
        url = reverse("management:user-profile", args=[self.sampler.pk])
        response = self.client.post(url, {"username": self.admin.username, "first_name": "王五"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("username", response.json()["errors"])
        self.client.force_login(self.sampler)
        self.assertEqual(self.client.post(url, {"username": "renamed", "first_name": "王五"}).status_code, 403)

    def test_inline_role_change_preserves_profile_and_requires_admin(self):
        self.sampler.first_name = "张三"
        self.sampler.save()
        url = reverse("management:user-role", args=[self.sampler.pk])
        response = self.client.post(url, {"role": "admin"})
        self.assertEqual(response.status_code, 200)
        self.sampler.refresh_from_db()
        self.assertEqual(self.sampler.role, "admin")
        self.assertEqual(self.sampler.first_name, "张三")
        self.sampler.role = "sampler"
        self.sampler.save()
        self.client.force_login(self.sampler)
        self.assertEqual(self.client.post(url, {"role": "admin"}).status_code, 403)

    def test_inline_role_change_rejects_self_demotion_and_grouped_sampler(self):
        response = self.client.post(reverse("management:user-role", args=[self.admin.pk]), {"role": "sampler"})
        self.assertEqual(response.status_code, 400)
        group = PersonnelGroup.objects.create(name="测试组", created_by=self.admin)
        group.members.add(self.sampler)
        response = self.client.post(reverse("management:user-role", args=[self.sampler.pk]), {"role": "admin"})
        self.assertEqual(response.status_code, 400)
        self.sampler.refresh_from_db()
        self.assertEqual(self.sampler.role, "sampler")

    def test_password_drawer_returns_validation_errors_and_saves(self):
        url = reverse("management:user-reset-password", args=[self.sampler.pk])
        response = self.client.post(url, {"password1": "Strong729!New", "password2": "different"}, HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("new_password2", response.json()["errors"])
        response = self.client.post(url, {"password1": "Strong729!New", "password2": "Strong729!New"}, HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 200)
        self.sampler.refresh_from_db()
        self.assertTrue(self.sampler.check_password("Strong729!New"))

    def test_create_dialog_uses_compact_form_and_defaults(self):
        response = self.client.get(reverse("management:user-create"))
        form = response.context["form"]
        self.assertEqual(set(form.fields), {"username", "password1", "first_name", "role"})
        self.assertEqual(form["role"].value(), User.Role.SAMPLER)
        self.assertEqual(list(form.fields["role"].choices), list(User.Role.choices))
        self.assertContains(response, 'id="user-create-dialog"')

    def test_create_with_single_password_and_show_duplicate_in_dialog(self):
        data = {"username": "new_person", "password1": "StrongRandom729!", "first_name": "张三", "role": "sampler"}
        response = self.client.post(reverse("management:user-create"), data)
        self.assertRedirects(response, reverse("management:user-list"))
        user = User.objects.get(username="new_person")
        self.assertTrue(user.check_password(data["password1"]))
        self.assertEqual(user.get_full_name(), "张三")
        self.assertTrue(user.is_active)
        response = self.client.post(reverse("management:user-create"), data)
        self.assertTrue(response.context["open_dialog"])
        self.assertIn("username", response.context["form"].errors)

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

    def test_admin_cannot_disable_current_account_through_edit_form(self):
        response = self.client.post(
            reverse("management:user-edit", args=[self.admin.pk]),
            {
                "username": self.admin.username,
                "role": User.Role.ADMIN,
                "first_name": "",
                "last_name": "",
                "phone": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)
        self.assertContains(response, "不能停用当前登录账号")

    def test_admin_cannot_demote_current_account_through_edit_form(self):
        response = self.client.post(
            reverse("management:user-edit", args=[self.admin.pk]),
            {
                "username": self.admin.username,
                "role": User.Role.SAMPLER,
                "first_name": "",
                "last_name": "",
                "phone": "",
                "is_active": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.role, User.Role.ADMIN)
        self.assertContains(response, "当前登录账号必须保留管理员角色")

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
