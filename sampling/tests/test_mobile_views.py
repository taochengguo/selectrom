from django.contrib.staticfiles import finders
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import User
from sampling.models import PersonnelAssignment, SamplingBatch, SamplingTask
from sampling.services.drawing import draw_materials
from sampling.tests.factories import SamplingFixturesMixin


class MobileTaskTests(SamplingFixturesMixin, TestCase):
    def test_sampling_animation_is_discoverable_by_django_staticfiles(self):
        self.assertIsNotNone(finders.find("js/sampling-animation.js"))

    def test_sampler_cannot_view_or_mutate_another_samplers_task(self):
        task, _assigned_sampler, _ = self.make_assigned_task()
        other_sampler = User.objects.create_user(
            "other_sampler", role=User.Role.SAMPLER
        )
        self.client.force_login(other_sampler)

        responses = [
            self.client.get(reverse("mobile:task-detail", args=[task.id])),
            self.client.post(reverse("mobile:task-draw", args=[task.id])),
            self.client.post(reverse("mobile:task-complete", args=[task.id])),
        ]

        self.assertEqual([response.status_code for response in responses], [404, 404, 404])
        task.refresh_from_db()
        self.assertEqual(task.status, SamplingTask.Status.ASSIGNED)
        self.assertFalse(SamplingBatch.objects.filter(task=task).exists())

    def test_administrator_is_forbidden_from_mobile_pages(self):
        task, _sampler, _ = self.make_assigned_task()
        self.client.force_login(task.created_by)

        responses = [
            self.client.get(reverse("mobile:dashboard")),
            self.client.get(reverse("mobile:reminders")),
            self.client.get(reverse("mobile:task-detail", args=[task.id])),
            self.client.get(reverse("mobile:profile")),
        ]

        self.assertEqual([response.status_code for response in responses], [403, 403, 403, 403])

    def test_dashboard_only_contains_current_users_assignments(self):
        own_task, sampler, _ = self.make_assigned_task()
        other_sampler = User.objects.create_user(
            "dashboard_other", role=User.Role.SAMPLER
        )
        other_task = SamplingTask.objects.create(
            task_number="DASH-OTHER",
            name="其他人员任务",
            personnel_group=own_task.personnel_group,
            draw_count=1,
            status=SamplingTask.Status.ASSIGNED,
            created_by=own_task.created_by,
        )
        PersonnelAssignment.objects.create(
            task=other_task,
            candidate_user_ids=[other_sampler.id],
            selected_user=other_sampler,
            kind=PersonnelAssignment.Kind.INITIAL,
            is_current=True,
            created_by=own_task.created_by,
        )
        self.client.force_login(sampler)

        response = self.client.get(reverse("mobile:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, own_task.task_number)
        self.assertNotContains(response, other_task.task_number)

    def test_reminders_filter_status_and_mark_unread_from_current_assignment(self):
        assigned_task, sampler, _ = self.make_assigned_task()
        completed_task = SamplingTask.objects.create(
            task_number="DONE-1",
            name="已完成任务",
            personnel_group=assigned_task.personnel_group,
            draw_count=1,
            status=SamplingTask.Status.COMPLETED,
            created_by=assigned_task.created_by,
        )
        PersonnelAssignment.objects.create(
            task=completed_task,
            candidate_user_ids=[sampler.id],
            selected_user=sampler,
            kind=PersonnelAssignment.Kind.INITIAL,
            is_current=True,
            created_by=assigned_task.created_by,
        )
        self.client.force_login(sampler)

        response = self.client.get(
            reverse("mobile:reminders"), {"status": SamplingTask.Status.ASSIGNED}
        )

        self.assertContains(response, assigned_task.task_number)
        self.assertContains(response, "未读")
        self.assertNotContains(response, completed_task.task_number)

    def test_opening_detail_sets_current_assignment_viewed_at_once(self):
        task, sampler, _ = self.make_assigned_task()
        assignment = task.personnel_assignments.get(is_current=True)
        self.client.force_login(sampler)

        first_response = self.client.get(reverse("mobile:task-detail", args=[task.id]))
        assignment.refresh_from_db()
        first_viewed_at = assignment.viewed_at
        second_response = self.client.get(reverse("mobile:task-detail", args=[task.id]))
        assignment.refresh_from_db()

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertIsNotNone(first_viewed_at)
        self.assertEqual(assignment.viewed_at, first_viewed_at)

    def test_draw_response_uses_server_persisted_locked_results(self):
        task, sampler, _ = self.make_assigned_task(draw_count=2, pool_size=3)
        self.client.force_login(sampler)

        response = self.client.post(reverse("mobile:task-draw", args=[task.id]))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        batch = SamplingBatch.objects.get(pk=payload["batch_id"])
        persisted = list(
            batch.results.select_related("material")
            .order_by("sequence")
            .values_list("material__material_number", flat=True)
        )
        self.assertEqual(payload["batch_status"], SamplingBatch.Status.LOCKED)
        self.assertEqual(
            [item["material_number"] for item in payload["results"]], persisted
        )
        self.assertEqual(len(payload["results"]), task.draw_count)
        self.assertEqual(
            set(payload["results"][0]),
            {
                "sequence",
                "material_number",
                "order_number",
                "supplier",
                "material_name",
                "quantity",
                "sampling_quantity",
            },
        )

    def test_repeat_draw_and_detail_refresh_show_same_locked_result(self):
        task, sampler, _ = self.make_assigned_task(draw_count=2, pool_size=3)
        self.client.force_login(sampler)

        first_payload = self.client.post(
            reverse("mobile:task-draw", args=[task.id])
        ).json()
        repeated_payload = self.client.post(
            reverse("mobile:task-draw", args=[task.id])
        ).json()
        detail = self.client.get(reverse("mobile:task-detail", args=[task.id]))

        self.assertEqual(repeated_payload, first_payload)
        self.assertEqual(SamplingBatch.objects.filter(task=task).count(), 1)
        for result in first_payload["results"]:
            self.assertContains(detail, result["material_number"])

    def test_completion_uses_locked_result_and_is_idempotent(self):
        task, sampler, _ = self.make_assigned_task()
        self.client.force_login(sampler)
        draw_materials(task_id=task.id, actor=sampler)

        first = self.client.post(reverse("mobile:task-complete", args=[task.id]))
        second = self.client.post(reverse("mobile:task-complete", args=[task.id]))

        self.assertRedirects(first, reverse("mobile:task-detail", args=[task.id]))
        self.assertRedirects(second, reverse("mobile:task-detail", args=[task.id]))
        task.refresh_from_db()
        self.assertEqual(task.status, SamplingTask.Status.COMPLETED)

    def test_writes_reject_get_and_require_csrf(self):
        task, sampler, _ = self.make_assigned_task()
        self.client.force_login(sampler)

        self.assertEqual(
            self.client.get(reverse("mobile:task-draw", args=[task.id])).status_code,
            405,
        )
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(sampler)
        self.assertEqual(
            csrf_client.post(reverse("mobile:task-draw", args=[task.id])).status_code,
            403,
        )


class MobileProfileTests(TestCase):
    def setUp(self):
        self.sampler = User.objects.create_user(
            "profile_sampler",
            role=User.Role.SAMPLER,
            first_name="旧名",
            last_name="旧姓",
            phone="10086",
            is_active=True,
        )
        self.client.force_login(self.sampler)

    def test_profile_updates_only_safe_fields(self):
        response = self.client.post(
            reverse("mobile:profile"),
            {
                "first_name": "新名",
                "last_name": "新姓",
                "phone": "13800000000",
                "username": "taken-over",
                "role": User.Role.ADMIN,
                "is_active": "",
            },
        )

        self.assertRedirects(response, reverse("mobile:profile"))
        self.sampler.refresh_from_db()
        self.assertEqual(self.sampler.first_name, "新名")
        self.assertEqual(self.sampler.last_name, "新姓")
        self.assertEqual(self.sampler.phone, "13800000000")
        self.assertEqual(self.sampler.username, "profile_sampler")
        self.assertEqual(self.sampler.role, User.Role.SAMPLER)
        self.assertTrue(self.sampler.is_active)

    def test_profile_post_requires_csrf(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.sampler)

        response = csrf_client.post(reverse("mobile:profile"), {"phone": "123"})

        self.assertEqual(response.status_code, 403)

    def test_profile_can_change_password_without_logging_out(self):
        self.sampler.set_password("Old-password-123")
        self.sampler.save(update_fields=["password"])
        self.client.force_login(self.sampler)

        response = self.client.post(
            reverse("mobile:profile"),
            {
                "action": "change_password",
                "old_password": "Old-password-123",
                "new_password1": "New-password-456",
                "new_password2": "New-password-456",
            },
        )

        self.assertRedirects(response, reverse("mobile:profile"))
        self.sampler.refresh_from_db()
        self.assertTrue(self.sampler.check_password("New-password-456"))
        self.assertEqual(
            self.client.get(reverse("mobile:profile")).status_code,
            200,
        )
