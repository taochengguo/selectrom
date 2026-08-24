from unittest.mock import patch

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

    def test_seed_demo_rolls_back_tasks_when_candidate_creation_fails(self):
        real_create = CandidateMaterial.objects.create
        attempts = 0

        def fail_on_second_candidate(*args, **kwargs):
            nonlocal attempts
            attempts += 1
            if attempts == 2:
                raise RuntimeError("simulated candidate failure")
            return real_create(*args, **kwargs)

        with patch(
            "sampling.management.commands.seed_demo.CandidateMaterial.objects.create",
            side_effect=fail_on_second_candidate,
        ):
            with self.assertRaisesRegex(RuntimeError, "simulated candidate failure"):
                call_command("seed_demo")

        self.assertFalse(SamplingTask.objects.filter(task_number="DEMO-DRAFT-001").exists())
        self.assertFalse(SamplingTask.objects.filter(task_number="DEMO-READY-001").exists())
        self.assertEqual(CandidateMaterial.objects.count(), 0)

        call_command("seed_demo")
        ready_task = SamplingTask.objects.get(task_number="DEMO-READY-001")
        self.assertEqual(ready_task.candidates.count(), 10)

    def test_seed_demo_preserves_existing_partial_task_without_repairing_it(self):
        custom_admin = User.objects.create_user("partial_admin", role=User.Role.ADMIN)
        custom_sampler = User.objects.create_user("partial_sampler", role=User.Role.SAMPLER)
        custom_group = PersonnelGroup.objects.create(name="partial_group", created_by=custom_admin)
        custom_group.members.add(custom_sampler)
        partial_task = SamplingTask.objects.create(
            task_number="DEMO-READY-001",
            name="manual partial task",
            personnel_group=custom_group,
            draw_count=1,
            status=SamplingTask.Status.DRAFT,
            notes="manual partial notes",
            created_by=custom_admin,
        )

        call_command("seed_demo")

        partial_task.refresh_from_db()
        self.assertEqual(partial_task.name, "manual partial task")
        self.assertEqual(partial_task.personnel_group_id, custom_group.id)
        self.assertEqual(partial_task.draw_count, 1)
        self.assertEqual(partial_task.status, SamplingTask.Status.DRAFT)
        self.assertEqual(partial_task.notes, "manual partial notes")
        self.assertEqual(partial_task.created_by_id, custom_admin.id)
        self.assertEqual(partial_task.candidates.count(), 0)

    def test_seed_demo_restores_documented_account_fields_after_drift(self):
        call_command("seed_demo")
        admin = User.objects.get(username="demo_admin")
        sampler = User.objects.get(username="demo_sampler_01")

        admin.role = User.Role.SAMPLER
        admin.is_active = False
        admin.first_name = "drifted admin"
        admin.set_password("changed-demo-password")
        admin.save(update_fields=["role", "is_active", "first_name", "password"])
        sampler.role = User.Role.ADMIN
        sampler.is_active = False
        sampler.first_name = "drifted sampler"
        sampler.set_password("changed-demo-password")
        sampler.save(update_fields=["role", "is_active", "first_name", "password"])

        call_command("seed_demo")

        admin.refresh_from_db()
        sampler.refresh_from_db()
        self.assertEqual(admin.role, User.Role.ADMIN)
        self.assertTrue(admin.is_active)
        self.assertEqual(admin.first_name, "\u6f14\u793a\u7ba1\u7406\u5458")
        self.assertTrue(admin.check_password("demo123456"))
        self.assertEqual(sampler.role, User.Role.SAMPLER)
        self.assertTrue(sampler.is_active)
        self.assertEqual(sampler.first_name, "\u6f14\u793a\u62bd\u6837\u5458\u4e00")
        self.assertTrue(sampler.check_password("demo123456"))
