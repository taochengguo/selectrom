from unittest.mock import patch

from django.test import TestCase

from accounts.models import User
from audit.models import TaskAuditLog
from sampling.models import SamplingBatch, SamplingResult, SamplingTask
from sampling.services.drawing import authorize_redraw, complete_task, draw_materials
from sampling.tests.factories import SamplingFixturesMixin


class DrawingTests(SamplingFixturesMixin, TestCase):
    @patch("sampling.services.drawing.secrets.SystemRandom.sample")
    def test_draw_persists_unique_ordered_results(self, sample):
        task, sampler, materials = self.make_assigned_task(draw_count=2, pool_size=3)
        sample.return_value = [materials[2].id, materials[0].id]

        batch = draw_materials(task_id=task.id, actor=sampler)

        self.assertEqual(batch.status, SamplingBatch.Status.LOCKED)
        self.assertEqual(batch.kind, SamplingBatch.Kind.INITIAL)
        self.assertEqual(
            list(
                SamplingResult.objects.filter(batch=batch)
                .order_by("sequence")
                .values_list("material_id", flat=True)
            ),
            [materials[2].id, materials[0].id],
        )
        task.refresh_from_db()
        self.assertEqual(task.status, SamplingTask.Status.IN_PROGRESS)
        audit = TaskAuditLog.objects.get(task=task, event_type="draw.initial")
        self.assertEqual(audit.after_data["batch_id"], batch.id)
        self.assertEqual(audit.after_data["material_ids"], [materials[2].id, materials[0].id])

    def test_only_current_sampler_can_draw_or_complete(self):
        task, sampler, _ = self.make_assigned_task()
        other_sampler = User.objects.create_user("other_sampler", role=User.Role.SAMPLER)

        with self.assertRaisesRegex(ValueError, "当前抽样人员"):
            draw_materials(task_id=task.id, actor=other_sampler)

        batch = draw_materials(task_id=task.id, actor=sampler)
        with self.assertRaisesRegex(ValueError, "当前抽样人员"):
            complete_task(task_id=task.id, actor=other_sampler)

        batch.refresh_from_db()
        self.assertEqual(batch.status, SamplingBatch.Status.LOCKED)
        task.refresh_from_db()
        self.assertEqual(task.status, SamplingTask.Status.IN_PROGRESS)

    @patch("sampling.services.drawing.secrets.SystemRandom.sample")
    def test_repeat_initial_draw_returns_locked_batch_without_sampling_again(self, sample):
        task, sampler, materials = self.make_assigned_task(draw_count=2)
        sample.return_value = [materials[1].id, materials[0].id]
        initial = draw_materials(task_id=task.id, actor=sampler)
        sample.reset_mock()

        repeated = draw_materials(task_id=task.id, actor=sampler)

        self.assertEqual(repeated.id, initial.id)
        sample.assert_not_called()
        self.assertEqual(SamplingBatch.objects.filter(task=task).count(), 1)
        self.assertEqual(SamplingResult.objects.filter(batch=initial).count(), 2)

    def test_repeated_draw_does_not_create_an_unauthorized_redraw(self):
        task, sampler, _ = self.make_assigned_task()
        initial = draw_materials(task_id=task.id, actor=sampler)

        repeated = draw_materials(task_id=task.id, actor=sampler)

        self.assertEqual(repeated.id, initial.id)
        self.assertEqual(SamplingBatch.objects.filter(task=task).count(), 1)

    def test_redraw_authorization_requires_admin_and_nonblank_reason(self):
        task, sampler, _ = self.make_assigned_task()
        draw_materials(task_id=task.id, actor=sampler)
        admin = task.created_by

        with self.assertRaisesRegex(ValueError, "管理员"):
            authorize_redraw(task_id=task.id, actor=sampler, reason="重新抽样")
        with self.assertRaisesRegex(ValueError, "重抽原因不能为空"):
            authorize_redraw(task_id=task.id, actor=admin, reason="   ")

        self.assertEqual(SamplingBatch.objects.filter(task=task).count(), 1)
        task.refresh_from_db()
        self.assertEqual(task.status, SamplingTask.Status.IN_PROGRESS)

    @patch("sampling.services.drawing.secrets.SystemRandom.sample")
    def test_authorized_redraw_creates_new_version_and_preserves_history(self, sample):
        task, sampler, materials = self.make_assigned_task(draw_count=2)
        sample.side_effect = [
            [materials[0].id, materials[1].id],
            [materials[2].id, materials[0].id],
        ]
        initial = draw_materials(task_id=task.id, actor=sampler)
        initial_material_ids = list(
            initial.results.order_by("sequence").values_list("material_id", flat=True)
        )

        redraw = authorize_redraw(
            task_id=task.id, actor=task.created_by, reason="结果需复核"
        )

        self.assertEqual(redraw.version, 2)
        self.assertEqual(redraw.kind, SamplingBatch.Kind.REDRAW)
        self.assertEqual(redraw.status, SamplingBatch.Status.AUTHORIZED)
        self.assertEqual(redraw.reason, "结果需复核")
        task.refresh_from_db()
        self.assertEqual(task.status, SamplingTask.Status.ASSIGNED)
        self.assertEqual(task.personnel_assignments.get(is_current=True).selected_user_id, sampler.id)

        locked_redraw = draw_materials(task_id=task.id, actor=sampler)

        self.assertEqual(locked_redraw.id, redraw.id)
        self.assertEqual(locked_redraw.status, SamplingBatch.Status.LOCKED)
        self.assertEqual(
            list(initial.results.order_by("sequence").values_list("material_id", flat=True)),
            initial_material_ids,
        )
        self.assertEqual(
            list(
                locked_redraw.results.order_by("sequence").values_list("material_id", flat=True)
            ),
            [materials[2].id, materials[0].id],
        )
        self.assertEqual(
            list(
                TaskAuditLog.objects.filter(task=task)
                .order_by("id")
                .values_list("event_type", flat=True)
            ),
            ["draw.initial", "draw.redraw_authorized", "draw.redraw"],
        )

    def test_completion_requires_locked_batch_and_is_idempotent(self):
        task, sampler, _ = self.make_assigned_task()
        task.status = SamplingTask.Status.IN_PROGRESS
        task.save(update_fields=["status", "updated_at"])

        with self.assertRaisesRegex(ValueError, "锁定的抽样批次"):
            complete_task(task_id=task.id, actor=sampler)

        task.status = SamplingTask.Status.ASSIGNED
        task.save(update_fields=["status", "updated_at"])
        draw_materials(task_id=task.id, actor=sampler)
        completed = complete_task(task_id=task.id, actor=sampler)
        repeated = complete_task(task_id=task.id, actor=sampler)

        self.assertEqual(completed.status, SamplingTask.Status.COMPLETED)
        self.assertEqual(repeated.id, completed.id)
        self.assertEqual(
            TaskAuditLog.objects.filter(task=task, event_type="task.completed").count(), 1
        )
