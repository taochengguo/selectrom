from unittest.mock import patch

from django.test import TestCase

from accounts.models import User
from audit.models import TaskAuditLog
from personnel.models import PersonnelGroup
from sampling.models import PersonnelAssignment, SamplingTask
from sampling.services.assignment import assign_sampler, reassign_sampler


class AssignmentTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("admin", role=User.Role.ADMIN)
        self.active = User.objects.create_user(
            "active", role=User.Role.SAMPLER, is_active=True
        )
        self.inactive = User.objects.create_user(
            "inactive", role=User.Role.SAMPLER, is_active=False
        )
        self.group = PersonnelGroup.objects.create(name="第一组", created_by=self.admin)

    def make_task(self, *, status=SamplingTask.Status.READY):
        return SamplingTask.objects.create(
            task_number=f"T-{SamplingTask.objects.count() + 1}",
            name="任务",
            personnel_group=self.group,
            draw_count=1,
            status=status,
            created_by=self.admin,
        )

    @patch("sampling.services.assignment.secrets.choice")
    def test_assignment_snapshots_every_group_member_without_filtering(self, choice):
        self.group.members.add(self.active, self.inactive)
        task = self.make_task()
        choice.return_value = self.inactive.id

        assignment = assign_sampler(task_id=task.id, actor=self.admin)

        self.assertEqual(
            sorted(assignment.candidate_user_ids), sorted([self.active.id, self.inactive.id])
        )
        self.assertEqual(assignment.selected_user, self.inactive)
        task.refresh_from_db()
        self.assertEqual(task.status, SamplingTask.Status.ASSIGNED)

    def test_assignment_rejects_empty_group_without_persisting_changes(self):
        task = self.make_task()

        with self.assertRaisesRegex(ValueError, "抽样人员分组不能为空"):
            assign_sampler(task_id=task.id, actor=self.admin)

        task.refresh_from_db()
        self.assertEqual(task.status, SamplingTask.Status.READY)
        self.assertFalse(PersonnelAssignment.objects.filter(task=task).exists())
        self.assertFalse(TaskAuditLog.objects.filter(task=task).exists())

    def test_assignment_requires_ready_task_and_cannot_create_a_second_initial_assignment(self):
        self.group.members.add(self.active)
        task = self.make_task(status=SamplingTask.Status.DRAFT)

        with self.assertRaisesRegex(ValueError, "任务当前状态不可执行"):
            assign_sampler(task_id=task.id, actor=self.admin)

        task.status = SamplingTask.Status.READY
        task.save(update_fields=["status", "updated_at"])
        assign_sampler(task_id=task.id, actor=self.admin)

        with self.assertRaisesRegex(ValueError, "任务当前状态不可执行"):
            assign_sampler(task_id=task.id, actor=self.admin)

        self.assertEqual(
            PersonnelAssignment.objects.filter(
                task=task, kind=PersonnelAssignment.Kind.INITIAL
            ).count(),
            1,
        )

    @patch("sampling.services.assignment.secrets.choice")
    def test_assignment_records_snapshot_and_selected_user_in_audit_event(self, choice):
        self.group.members.add(self.active, self.inactive)
        task = self.make_task()
        choice.return_value = self.active.id

        assignment = assign_sampler(task_id=task.id, actor=self.admin)

        audit = TaskAuditLog.objects.get(task=task, event_type="assignment.initial")
        self.assertEqual(sorted(audit.after_data["candidate_user_ids"]), sorted([self.active.id, self.inactive.id]))
        self.assertEqual(audit.after_data["selected_user_id"], assignment.selected_user_id)
        self.assertEqual(audit.after_data["assignment_id"], assignment.id)

    def test_reassignment_requires_a_nonblank_reason(self):
        self.group.members.add(self.active)
        task = self.make_task(status=SamplingTask.Status.ASSIGNED)
        original = PersonnelAssignment.objects.create(
            task=task,
            candidate_user_ids=[self.active.id],
            selected_user=self.active,
            kind=PersonnelAssignment.Kind.INITIAL,
            is_current=True,
            created_by=self.admin,
        )

        with self.assertRaisesRegex(ValueError, "重分配原因不能为空"):
            reassign_sampler(task_id=task.id, actor=self.admin, reason="   ")

        original.refresh_from_db()
        self.assertTrue(original.is_current)
        self.assertEqual(PersonnelAssignment.objects.filter(task=task).count(), 1)

    @patch("sampling.services.assignment.secrets.choice")
    def test_reassignment_retains_noncurrent_history_and_can_select_same_user(self, choice):
        self.group.members.add(self.active, self.inactive)
        task = self.make_task(status=SamplingTask.Status.ASSIGNED)
        original = PersonnelAssignment.objects.create(
            task=task,
            candidate_user_ids=[self.active.id],
            selected_user=self.active,
            kind=PersonnelAssignment.Kind.INITIAL,
            is_current=True,
            created_by=self.admin,
        )
        choice.return_value = self.active.id

        reassignment = reassign_sampler(
            task_id=task.id, actor=self.admin, reason="需要重新安排"
        )

        original.refresh_from_db()
        self.assertFalse(original.is_current)
        self.assertTrue(reassignment.is_current)
        self.assertEqual(reassignment.kind, PersonnelAssignment.Kind.REASSIGN)
        self.assertEqual(reassignment.reason, "需要重新安排")
        self.assertEqual(reassignment.selected_user, self.active)
        self.assertEqual(
            sorted(reassignment.candidate_user_ids),
            sorted([self.active.id, self.inactive.id]),
        )
        self.assertEqual(PersonnelAssignment.objects.filter(task=task, is_current=True).count(), 1)

        audit = TaskAuditLog.objects.get(task=task, event_type="assignment.reassigned")
        self.assertEqual(audit.before_data["assignment_id"], original.id)
        self.assertEqual(audit.before_data["selected_user_id"], self.active.id)
        self.assertEqual(audit.after_data["assignment_id"], reassignment.id)
        self.assertEqual(audit.after_data["selected_user_id"], self.active.id)
