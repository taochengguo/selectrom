from django.test import TestCase

from accounts.models import User
from audit.models import TaskAuditLog
from audit.services import log_task_event
from personnel.models import PersonnelGroup
from sampling.models import SamplingTask


class AuditTests(TestCase):
    def test_only_explicit_task_event_creates_log(self):
        admin = User.objects.create_user("admin", role=User.Role.ADMIN)
        group = PersonnelGroup.objects.create(name="第一组", created_by=admin)
        task = SamplingTask.objects.create(
            task_number="T-1",
            name="任务",
            personnel_group=group,
            draw_count=1,
            created_by=admin,
        )

        admin.phone = "13800000000"
        admin.save()

        self.assertEqual(TaskAuditLog.objects.count(), 0)

        log_task_event(
            task=task,
            actor=admin,
            event_type="task.created",
            after={"status": "draft"},
        )

        self.assertEqual(TaskAuditLog.objects.count(), 1)
