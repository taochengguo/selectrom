from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from personnel.forms import PersonnelGroupForm
from personnel.models import PersonnelGroup


class PersonnelGroupTests(TestCase):
    def test_bulk_delete_preserves_users_and_protected_groups(self):
        from sampling.models import SamplingTask
        free = PersonnelGroup.objects.create(name="可删除", created_by=self.owner)
        free.members.add(self.sampler)
        protected = PersonnelGroup.objects.create(name="有关联任务", created_by=self.owner)
        SamplingTask.objects.create(task_number="KEEP-1", name="任务", personnel_group=protected, created_by=self.owner)
        self.client.force_login(self.owner)
        url = reverse("personnel:group-bulk-delete")
        self.assertEqual(self.client.get(url).status_code, 405)
        response = self.client.post(url, {"groups": [free.pk, protected.pk]})
        self.assertRedirects(response, reverse("personnel:group-list"))
        self.assertFalse(PersonnelGroup.objects.filter(pk=free.pk).exists())
        self.assertTrue(PersonnelGroup.objects.filter(pk=protected.pk).exists())
        self.assertTrue(User.objects.filter(pk=self.sampler.pk).exists())

    def test_bulk_delete_rejects_invalid_selection_and_sampler(self):
        group = PersonnelGroup.objects.create(name="保留", created_by=self.owner)
        url = reverse("personnel:group-bulk-delete")
        self.client.force_login(self.owner)
        for selection in ([], [group.pk, 999999], ["invalid"]):
            self.client.post(url, {"groups": selection})
            self.assertTrue(PersonnelGroup.objects.filter(pk=group.pk).exists())
        self.client.force_login(self.sampler)
        self.assertEqual(self.client.post(url, {"groups": [group.pk]}).status_code, 403)

    def test_edit_dialog_prefills_name_description_and_selected_members(self):
        group = PersonnelGroup.objects.create(name="现有组", description="现有说明", created_by=self.owner)
        group.members.add(self.sampler)
        self.client.force_login(self.owner)
        url = reverse("personnel:group-edit", args=[group.pk])
        response = self.client.get(url)
        self.assertTrue(response.context["open_group_dialog"])
        self.assertContains(response, 'id="group-create-dialog"')
        self.assertContains(response, "保存修改")
        self.assertEqual(response.context["form"]["name"].value(), "现有组")
        self.assertEqual(response.context["form"]["description"].value(), "现有说明")
        self.assertIn(self.sampler.pk, response.context["form"]["members"].value())
        response = self.client.post(url, {"name": "", "description": "修改说明", "members": [self.sampler.pk]})
        self.assertTrue(response.context["open_group_dialog"])
        self.assertIn("name", response.context["form"].errors)
        group.refresh_from_db()
        self.assertEqual(group.name, "现有组")

    def test_create_dialog_has_named_checkboxes_and_optional_description(self):
        self.sampler.first_name = "张三"
        self.sampler.save()
        self.client.force_login(self.owner)
        response = self.client.get(reverse("personnel:group-create"))
        self.assertTrue(response.context["open_group_dialog"])
        self.assertContains(response, 'id="group-create-dialog"')
        self.assertContains(response, 'type="checkbox"')
        self.assertContains(response, "张三")
        self.assertFalse(response.context["form"].fields["description"].required)
        response = self.client.post(reverse("personnel:group-create"), {"name": "", "members": [self.sampler.pk]})
        self.assertTrue(response.context["open_group_dialog"])
        self.assertIn("name", response.context["form"].errors)
        self.assertEqual(list(response.context["form"].cleaned_data["members"]), [self.sampler])

    def setUp(self):
        self.owner = User.objects.create_user("owner", role=User.Role.ADMIN)
        self.sampler = User.objects.create_user("s1", role=User.Role.SAMPLER)

    def test_group_accepts_sampler(self):
        group = PersonnelGroup.objects.create(name="第一组", created_by=self.owner)

        group.members.add(self.sampler)

        self.assertEqual(list(group.members.all()), [self.sampler])

    def test_group_rejects_admin_through_direct_member_add(self):
        admin = User.objects.create_user("a1", role=User.Role.ADMIN)
        group = PersonnelGroup.objects.create(name="第一组", created_by=self.owner)

        with self.assertRaises(ValidationError):
            group.members.add(admin)

    def test_group_form_offers_active_and_inactive_samplers_only(self):
        inactive_sampler = User.objects.create_user(
            "s2", role=User.Role.SAMPLER, is_active=False
        )
        User.objects.create_user("a1", role=User.Role.ADMIN)

        form = PersonnelGroupForm()

        self.assertEqual(
            set(form.fields["members"].queryset), {self.sampler, inactive_sampler}
        )

    def test_admin_can_create_group_and_becomes_creator(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse("personnel:group-create"),
            {"name": "第一组", "description": "说明", "members": [self.sampler.pk]},
        )

        group = PersonnelGroup.objects.get(name="第一组")
        self.assertRedirects(response, reverse("personnel:group-list"))
        self.assertEqual(group.created_by, self.owner)
        self.assertEqual(list(group.members.all()), [self.sampler])

    def test_edit_keeps_original_creator(self):
        another_admin = User.objects.create_user("a2", role=User.Role.ADMIN)
        group = PersonnelGroup.objects.create(name="第一组", created_by=self.owner)
        self.client.force_login(another_admin)

        response = self.client.post(
            reverse("personnel:group-edit", args=[group.pk]),
            {"name": "改名组", "description": "", "members": [self.sampler.pk]},
        )

        group.refresh_from_db()
        self.assertRedirects(response, reverse("personnel:group-list"))
        self.assertEqual(group.created_by, self.owner)
        self.assertEqual(group.name, "改名组")

    def test_sampler_cannot_access_group_list(self):
        self.client.force_login(self.sampler)

        response = self.client.get(reverse("personnel:group-list"))

        self.assertEqual(response.status_code, 403)
