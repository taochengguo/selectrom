from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from personnel.forms import PersonnelGroupForm
from personnel.models import PersonnelGroup


class PersonnelGroupTests(TestCase):
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
