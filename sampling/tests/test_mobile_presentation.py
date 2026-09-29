from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from sampling.models import PersonnelAssignment, SamplingTask
from sampling.tests.factories import SamplingFixturesMixin


class MobilePresentationTests(SamplingFixturesMixin, TestCase):
    def setUp(self):
        self.task, self.sampler, _ = self.make_assigned_task()
        self.task.name = "食品安全抽检"
        self.task.planned_at = timezone.now()
        self.task.save()
        self.client.force_login(self.sampler)
        self.later = SamplingTask.objects.create(
            task_number="LATER-1",
            name="药品检查",
            personnel_group=self.task.personnel_group,
            draw_count=1,
            status=SamplingTask.Status.COMPLETED,
            created_by=self.task.created_by,
            planned_at=timezone.now() + timedelta(days=2),
        )
        PersonnelAssignment.objects.create(
            task=self.later,
            selected_user=self.sampler,
            candidate_user_ids=[self.sampler.pk],
            kind=PersonnelAssignment.Kind.INITIAL,
            is_current=True,
            created_by=self.task.created_by,
        )

    def test_search_matches_name_and_number_and_combines_with_status(self):
        url = reverse("mobile:dashboard")
        response = self.client.get(url, {"q": "食品"})
        self.assertEqual([task.pk for task in response.context["recent_tasks"]], [self.task.pk])
        response = self.client.get(url, {"q": "LATER-1", "status": "assigned"})
        self.assertEqual(list(response.context["recent_tasks"]), [])

    def test_today_uses_planned_date_without_changing_global_counts(self):
        response = self.client.get(reverse("mobile:dashboard"), {"period": "today"})
        self.assertEqual([task.pk for task in response.context["recent_tasks"]], [self.task.pk])
        self.assertEqual(response.context["summary"]["today"], 1)
        self.assertEqual(response.context["summary"]["completed"], 1)

    def test_reminder_pending_count_is_independent_of_selected_tab(self):
        response = self.client.get(reverse("mobile:reminders"), {"status": "completed"})
        self.assertEqual(response.context["pending_count"], 1)
        self.assertContains(response, self.later.task_number)
        self.assertNotContains(response, self.task.task_number)

    def test_profile_shows_owned_task_counts(self):
        response = self.client.get(reverse("mobile:profile"))
        self.assertEqual(response.context["summary"]["total"], 2)
        self.assertEqual(response.context["summary"]["assigned"], 1)
        self.assertEqual(response.context["summary"]["completed"], 1)
