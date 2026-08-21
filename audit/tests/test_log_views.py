from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from audit.models import TaskAuditLog
from personnel.models import PersonnelGroup
from sampling.models import SamplingTask


class TaskLogViewTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("admin", role=User.Role.ADMIN)
        self.other_admin = User.objects.create_user("auditor", role=User.Role.ADMIN)
        self.sampler = User.objects.create_user("sampler", role=User.Role.SAMPLER)
        group = PersonnelGroup.objects.create(name="第一组", created_by=self.admin)
        self.task_a = SamplingTask.objects.create(
            task_number="TASK-A",
            name="任务甲",
            personnel_group=group,
            draw_count=1,
            created_by=self.admin,
        )
        self.task_b = SamplingTask.objects.create(
            task_number="TASK-B",
            name="任务乙",
            personnel_group=group,
            draw_count=1,
            created_by=self.admin,
        )
        self.matching = TaskAuditLog.objects.create(
            task=self.task_a, actor=self.admin, event_type="task.created"
        )
        TaskAuditLog.objects.create(
            task=self.task_b, actor=self.other_admin, event_type="task.cancelled"
        )
        self.client.force_login(self.admin)

    def test_filters_task_logs_by_exact_task_event_actor_and_date_range(self):
        today = timezone.localdate()

        response = self.client.get(
            reverse("management:log-list"),
            {
                "task_number": "TASK-A",
                "event_type": "task.created",
                "actor": "admin",
                "start_date": today.isoformat(),
                "end_date": today.isoformat(),
            },
        )

        self.assertEqual(list(response.context["logs"]), [self.matching])
        self.assertContains(response, "TASK-A")
        self.assertNotContains(response, "TASK-B")

    def test_task_and_actor_filters_are_exact_not_substring(self):
        response = self.client.get(
            reverse("management:log-list"), {"task_number": "TASK", "actor": "adm"}
        )

        self.assertEqual(list(response.context["logs"]), [])

    def test_sampler_cannot_open_task_log(self):
        self.client.force_login(self.sampler)

        response = self.client.get(reverse("management:log-list"))

        self.assertEqual(response.status_code, 403)
