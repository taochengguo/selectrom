from io import BytesIO

from django.test import TestCase

from accounts.models import User
from audit.models import TaskAuditLog
from personnel.models import PersonnelGroup
from sampling.models import CandidateMaterial, SamplingTask
from sampling.services.imports import CandidateImportError, import_candidates
from sampling.services.lifecycle import TaskFrozenError


class CandidateImportTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("admin", role=User.Role.ADMIN)
        self.group = PersonnelGroup.objects.create(name="第一组", created_by=self.admin)
        self.task = SamplingTask.objects.create(
            task_number="T-1",
            name="任务",
            personnel_group=self.group,
            draw_count=1,
            created_by=self.admin,
        )

    def test_invalid_row_rolls_back_entire_csv(self):
        content = (
            "物资编号,订单号,供应商,物资名称,物资数量\n"
            "M-1,O-1,S,N,10\n"
            "M-1,O-2,S,N,0\n"
        ).encode("utf-8-sig")

        with self.assertRaises(CandidateImportError) as error:
            import_candidates(task_id=self.task.id, actor=self.admin, csv_file=BytesIO(content))

        self.assertIn("第3行", str(error.exception))
        self.assertEqual(CandidateMaterial.objects.count(), 0)
        self.assertEqual(TaskAuditLog.objects.count(), 0)

    def test_requires_exact_chinese_headers(self):
        content = "物资编号,订单号,供应商,物资名称,数量\nM-1,O-1,S,N,10\n".encode("utf-8")

        with self.assertRaisesMessage(CandidateImportError, "CSV 表头必须为"):
            import_candidates(task_id=self.task.id, actor=self.admin, csv_file=BytesIO(content))

        self.assertEqual(CandidateMaterial.objects.count(), 0)

    def test_import_strips_values_and_records_audit_event(self):
        content = "物资编号,订单号,供应商,物资名称,物资数量\n M-1 , O-1 , 供应商 , 物资 , 10 \n".encode("utf-8")

        imported = import_candidates(task_id=self.task.id, actor=self.admin, csv_file=BytesIO(content))

        self.assertEqual(imported, 1)
        material = CandidateMaterial.objects.get()
        self.assertEqual(material.material_number, "M-1")
        audit = TaskAuditLog.objects.get()
        self.assertEqual(audit.event_type, "materials.imported")
        self.assertEqual(audit.after_data["count"], 1)

    def test_duplicate_material_number_against_task_is_rejected(self):
        CandidateMaterial.objects.create(
            task=self.task,
            material_number="M-1",
            order_number="O-0",
            supplier="已有供应商",
            material_name="已有物资",
            quantity=1,
        )
        content = "物资编号,订单号,供应商,物资名称,物资数量\nM-1,O-1,S,N,10\n".encode("utf-8")

        with self.assertRaises(CandidateImportError) as error:
            import_candidates(task_id=self.task.id, actor=self.admin, csv_file=BytesIO(content))

        self.assertIn("第2行", str(error.exception))
        self.assertEqual(CandidateMaterial.objects.count(), 1)

    def test_frozen_task_rejects_import(self):
        self.task.status = SamplingTask.Status.ASSIGNED
        self.task.save(update_fields=["status"])
        content = "物资编号,订单号,供应商,物资名称,物资数量\nM-1,O-1,S,N,10\n".encode("utf-8")

        with self.assertRaises(TaskFrozenError):
            import_candidates(task_id=self.task.id, actor=self.admin, csv_file=BytesIO(content))

        self.assertEqual(CandidateMaterial.objects.count(), 0)

    def test_model_validation_errors_are_reported_by_row_before_any_write(self):
        too_long_material_number = "M" * 101
        content = (
            "物资编号,订单号,供应商,物资名称,物资数量\n"
            f"{too_long_material_number},O-1,S,N,10\n"
        ).encode("utf-8")

        with self.assertRaises(CandidateImportError) as error:
            import_candidates(task_id=self.task.id, actor=self.admin, csv_file=BytesIO(content))

        self.assertIn("第2行", str(error.exception))
        self.assertEqual(CandidateMaterial.objects.count(), 0)
