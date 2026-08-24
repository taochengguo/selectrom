from django.test import TestCase

from accounts.models import User
from audit.models import TaskAuditLog
from personnel.models import PersonnelGroup
from sampling.models import CandidateMaterial, SamplingTask
from sampling.services.lifecycle import (
    TaskFrozenError,
    cancel_task,
    create_candidate,
    create_task,
    delete_candidate,
    mark_task_ready,
    update_candidate,
    update_task,
)


class TaskLifecycleTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("admin", role=User.Role.ADMIN)
        self.group = PersonnelGroup.objects.create(name="第一组", created_by=self.admin)
        self.other_group = PersonnelGroup.objects.create(name="第二组", created_by=self.admin)

    def test_create_task_validates_and_records_concrete_audit_data(self):
        task = create_task(
            actor=self.admin,
            task_number="T-1",
            name="任务",
            personnel_group=self.group,
            draw_count=1,
            notes="备注",
        )

        self.assertEqual(task.status, SamplingTask.Status.DRAFT)
        audit = TaskAuditLog.objects.get()
        self.assertEqual(audit.event_type, "task.created")
        self.assertEqual(audit.after_data["task_number"], "T-1")
        self.assertEqual(audit.after_data["personnel_group_id"], self.group.id)

    def test_update_task_updates_draft_task_and_records_before_after(self):
        task = self.make_task()

        updated = update_task(
            task_id=task.id,
            actor=self.admin,
            name="改名任务",
            personnel_group=self.other_group,
            draw_count=2,
        )

        self.assertEqual(updated.name, "改名任务")
        self.assertEqual(updated.personnel_group, self.other_group)
        audit = TaskAuditLog.objects.get(event_type="task.updated")
        self.assertEqual(audit.before_data["draw_count"], 1)
        self.assertEqual(audit.after_data["draw_count"], 2)

    def test_mark_ready_requires_sufficient_candidates_and_audits_status_change(self):
        task = self.make_task()
        create_candidate(task_id=task.id, actor=self.admin, **self.material_data("M-1"))

        ready_task = mark_task_ready(task_id=task.id, actor=self.admin)

        self.assertEqual(ready_task.status, SamplingTask.Status.READY)
        audit = TaskAuditLog.objects.get(event_type="task.ready")
        self.assertEqual(audit.before_data["status"], SamplingTask.Status.DRAFT)
        self.assertEqual(audit.after_data["status"], SamplingTask.Status.READY)

    def test_assigned_task_cannot_transition_back_to_ready(self):
        task = self.make_task(status=SamplingTask.Status.ASSIGNED)

        with self.assertRaises(TaskFrozenError):
            mark_task_ready(task_id=task.id, actor=self.admin)

        task.refresh_from_db()
        self.assertEqual(task.status, SamplingTask.Status.ASSIGNED)
        self.assertEqual(TaskAuditLog.objects.count(), 0)

    def test_cancel_task_records_status_change(self):
        task = self.make_task()

        cancelled = cancel_task(task_id=task.id, actor=self.admin)

        self.assertEqual(cancelled.status, SamplingTask.Status.CANCELLED)
        self.assertEqual(TaskAuditLog.objects.get().event_type, "task.cancelled")

    def test_repeated_cancel_is_idempotent_and_records_one_audit_event(self):
        task = self.make_task()

        first = cancel_task(task_id=task.id, actor=self.admin)
        second = cancel_task(task_id=task.id, actor=self.admin)

        self.assertEqual(first.id, second.id)
        self.assertEqual(second.status, SamplingTask.Status.CANCELLED)
        self.assertEqual(
            TaskAuditLog.objects.filter(task=task, event_type="task.cancelled").count(),
            1,
        )

    def test_cancel_accepts_every_non_cancelled_task_state(self):
        for index, status in enumerate(
            (
                SamplingTask.Status.DRAFT,
                SamplingTask.Status.READY,
                SamplingTask.Status.ASSIGNED,
                SamplingTask.Status.IN_PROGRESS,
                SamplingTask.Status.COMPLETED,
            ),
            start=1,
        ):
            with self.subTest(status=status):
                task = SamplingTask.objects.create(
                    task_number=f"CANCEL-{index}",
                    name="task",
                    personnel_group=self.group,
                    draw_count=1,
                    status=status,
                    created_by=self.admin,
                )

                cancelled = cancel_task(task_id=task.id, actor=self.admin)

                self.assertEqual(cancelled.status, SamplingTask.Status.CANCELLED)

    def test_cancel_rejects_an_unknown_source_state_without_audit(self):
        task = self.make_task()
        SamplingTask.objects.filter(pk=task.pk).update(status="unknown")

        with self.assertRaisesMessage(
            ValueError, "\u4efb\u52a1\u5f53\u524d\u72b6\u6001\u4e0d\u53ef\u53d6\u6d88"
        ):
            cancel_task(task_id=task.id, actor=self.admin)

        task.refresh_from_db()
        self.assertEqual(task.status, "unknown")
        self.assertFalse(TaskAuditLog.objects.filter(task=task).exists())

    def test_candidate_crud_records_lifecycle_audit_events(self):
        task = self.make_task()
        candidate = create_candidate(task_id=task.id, actor=self.admin, **self.material_data("M-1"))
        candidate = update_candidate(
            candidate_id=candidate.id, actor=self.admin, quantity=20, material_name="新物资"
        )
        delete_candidate(candidate_id=candidate.id, actor=self.admin)

        self.assertFalse(CandidateMaterial.objects.filter(id=candidate.id).exists())
        self.assertEqual(
            list(TaskAuditLog.objects.order_by("id").values_list("event_type", flat=True)),
            ["material.created", "material.updated", "material.deleted"],
        )
        delete_audit = TaskAuditLog.objects.get(event_type="material.deleted")
        self.assertEqual(delete_audit.before_data["material_number"], "M-1")
        self.assertEqual(delete_audit.after_data, {})

    def test_executed_task_rejects_candidate_edit(self):
        task = self.make_task(status=SamplingTask.Status.ASSIGNED)
        candidate = CandidateMaterial.objects.create(task=task, **self.material_data("M-1"))

        with self.assertRaises(TaskFrozenError):
            update_candidate(candidate_id=candidate.id, actor=self.admin, quantity=20)

        candidate.refresh_from_db()
        self.assertEqual(candidate.quantity, 10)

    def test_executed_task_rejects_task_group_and_draw_count_change(self):
        task = self.make_task(status=SamplingTask.Status.ASSIGNED)

        with self.assertRaises(TaskFrozenError):
            update_task(task_id=task.id, actor=self.admin, personnel_group=self.other_group)

        with self.assertRaises(TaskFrozenError):
            update_task(task_id=task.id, actor=self.admin, draw_count=2)

    def make_task(self, status=SamplingTask.Status.DRAFT):
        return SamplingTask.objects.create(
            task_number=f"T-{SamplingTask.objects.count() + 1}",
            name="任务",
            personnel_group=self.group,
            draw_count=1,
            status=status,
            created_by=self.admin,
        )

    @staticmethod
    def material_data(material_number):
        return {
            "material_number": material_number,
            "order_number": "O-1",
            "supplier": "供应商",
            "material_name": "物资",
            "quantity": 10,
        }
