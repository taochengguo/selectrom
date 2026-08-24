from django.core.management import call_command
from django.test import TestCase

from accounts.models import User
from audit.models import TaskAuditLog
from personnel.models import PersonnelGroup
from sampling.models import CandidateMaterial, SamplingResult, SamplingTask
from sampling.services.assignment import assign_sampler
from sampling.services.drawing import complete_task, draw_materials


class SeedDemoTests(TestCase):
    def test_seed_demo_is_idempotent(self):
        call_command("seed_demo")
        audit_count = TaskAuditLog.objects.count()
        call_command("seed_demo")

        admin = User.objects.get(username="demo_admin")
        self.assertTrue(admin.check_password("demo123456"))
        self.assertEqual(User.objects.filter(username="demo_admin").count(), 1)
        demo_samplers = User.objects.filter(username__startswith="demo_sampler_").order_by(
            "username"
        )
        self.assertEqual(demo_samplers.count(), 3)
        self.assertTrue(all(user.role == User.Role.SAMPLER for user in demo_samplers))
        group = PersonnelGroup.objects.get(name="演示抽样组")
        self.assertEqual(group.members.count(), 3)
        task = SamplingTask.objects.get(task_number="DEMO-READY-001")
        material_numbers = list(task.candidates.values_list("material_number", flat=True))
        self.assertEqual(len(material_numbers), 10)
        self.assertEqual(len(set(material_numbers)), 10)
        self.assertLessEqual(task.draw_count, len(material_numbers))
        self.assertEqual(TaskAuditLog.objects.count(), audit_count)

    def test_seed_demo_preserves_completed_task_history_and_group_members(self):
        call_command("seed_demo")
        admin = User.objects.get(username="demo_admin")
        task = SamplingTask.objects.get(task_number="DEMO-READY-001")
        group = task.personnel_group
        extra_sampler = User.objects.create_user(
            "extra_sampler", role=User.Role.SAMPLER, password="not-a-demo-password"
        )
        group.members.add(extra_sampler)

        assignment = assign_sampler(task_id=task.id, actor=admin)
        batch = draw_materials(task_id=task.id, actor=assignment.selected_user)
        complete_task(task_id=task.id, actor=assignment.selected_user)
        task.refresh_from_db()
        task.name = "保留的历史任务名称"
        task.notes = "保留的历史任务说明"
        task.save(update_fields=["name", "notes"])
        first_candidate = task.candidates.order_by("id").first()
        first_candidate.supplier = "保留的历史供应商"
        first_candidate.save(update_fields=["supplier"])

        task_snapshot = {
            "status": task.status,
            "personnel_group_id": task.personnel_group_id,
            "draw_count": task.draw_count,
            "name": task.name,
            "notes": task.notes,
            "created_by_id": task.created_by_id,
        }
        candidate_snapshot = list(
            task.candidates.order_by("id").values(
                "id",
                "material_number",
                "order_number",
                "supplier",
                "material_name",
                "quantity",
            )
        )
        assignment_snapshot = list(
            task.personnel_assignments.order_by("id").values(
                "id", "selected_user_id", "candidate_user_ids", "kind", "is_current", "reason"
            )
        )
        batch_snapshot = list(
            task.sampling_batches.order_by("id").values(
                "id", "version", "kind", "status", "drawn_by_id", "reason"
            )
        )
        result_snapshot = list(
            SamplingResult.objects.filter(batch=batch).order_by("id").values(
                "id", "batch_id", "material_id", "sequence"
            )
        )
        audit_snapshot = list(
            TaskAuditLog.objects.filter(task=task)
            .order_by("id")
            .values("id", "event_type", "before_data", "after_data")
        )

        call_command("seed_demo")

        task.refresh_from_db()
        self.assertEqual(
            {
                "status": task.status,
                "personnel_group_id": task.personnel_group_id,
                "draw_count": task.draw_count,
                "name": task.name,
                "notes": task.notes,
                "created_by_id": task.created_by_id,
            },
            task_snapshot,
        )
        self.assertTrue(group.members.filter(pk=extra_sampler.pk).exists())
        self.assertEqual(
            list(
                task.candidates.order_by("id").values(
                    "id",
                    "material_number",
                    "order_number",
                    "supplier",
                    "material_name",
                    "quantity",
                )
            ),
            candidate_snapshot,
        )
        self.assertEqual(
            list(
                task.personnel_assignments.order_by("id").values(
                    "id",
                    "selected_user_id",
                    "candidate_user_ids",
                    "kind",
                    "is_current",
                    "reason",
                )
            ),
            assignment_snapshot,
        )
        self.assertEqual(
            list(
                task.sampling_batches.order_by("id").values(
                    "id", "version", "kind", "status", "drawn_by_id", "reason"
                )
            ),
            batch_snapshot,
        )
        self.assertEqual(
            list(
                SamplingResult.objects.filter(batch=batch).order_by("id").values(
                    "id", "batch_id", "material_id", "sequence"
                )
            ),
            result_snapshot,
        )
        self.assertEqual(
            list(
                TaskAuditLog.objects.filter(task=task)
                .order_by("id")
                .values("id", "event_type", "before_data", "after_data")
            ),
            audit_snapshot,
        )
