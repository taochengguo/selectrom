from django.db import IntegrityError, transaction
from django.test import TestCase

from accounts.models import User
from personnel.models import PersonnelGroup
from sampling.models import CandidateMaterial, SamplingBatch, SamplingResult, SamplingTask


class SamplingModelTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("admin", role=User.Role.ADMIN)
        self.group = PersonnelGroup.objects.create(name="第一组", created_by=self.admin)
        self.task = SamplingTask.objects.create(
            task_number="T-001",
            name="入库抽样",
            personnel_group=self.group,
            draw_count=1,
            created_by=self.admin,
        )

    def test_material_number_is_unique_inside_task(self):
        values = dict(
            task=self.task,
            material_number="M-001",
            order_number="O-1",
            supplier="供应商",
            material_name="物资",
            quantity=10,
        )
        CandidateMaterial.objects.create(**values)

        with self.assertRaises(IntegrityError), transaction.atomic():
            CandidateMaterial.objects.create(**values)

    def test_draw_count_must_be_positive(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            SamplingTask.objects.create(
                task_number="T-002",
                name="无效抽样",
                personnel_group=self.group,
                draw_count=0,
                created_by=self.admin,
            )

    def test_material_quantity_must_be_positive(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            CandidateMaterial.objects.create(
                task=self.task,
                material_number="M-001",
                order_number="O-1",
                supplier="供应商",
                material_name="物资",
                quantity=0,
            )

    def test_task_cannot_be_ready_when_draw_count_exceeds_pool(self):
        with self.assertRaisesMessage(ValueError, "抽取数量不能超过候选物资数量"):
            self.task.mark_ready()

    def test_mark_ready_persists_ready_status_when_pool_is_sufficient(self):
        self.create_material("M-001")

        self.task.mark_ready()

        self.task.refresh_from_db()
        self.assertEqual(self.task.status, SamplingTask.Status.READY)

    def test_model_mark_ready_only_allows_draft_source_state(self):
        self.create_material("M-001")

        for status in (
            SamplingTask.Status.READY,
            SamplingTask.Status.ASSIGNED,
            SamplingTask.Status.IN_PROGRESS,
            SamplingTask.Status.COMPLETED,
            SamplingTask.Status.CANCELLED,
        ):
            with self.subTest(status=status):
                SamplingTask.objects.filter(pk=self.task.pk).update(status=status)
                self.task.refresh_from_db()

                with self.assertRaisesMessage(
                    ValueError,
                    "\u53ea\u6709\u8349\u7a3f\u4efb\u52a1\u53ef\u4ee5\u8bbe\u4e3a\u5f85\u6267\u884c",
                ):
                    self.task.mark_ready()

                self.task.refresh_from_db()
                self.assertEqual(self.task.status, status)

    def test_batch_version_is_unique_inside_task(self):
        self.create_batch(version=1)

        with self.assertRaises(IntegrityError), transaction.atomic():
            self.create_batch(version=1)

    def test_result_material_is_unique_inside_batch(self):
        material = self.create_material("M-001")
        batch = self.create_batch(version=1)
        SamplingResult.objects.create(batch=batch, material=material, sequence=1)

        with self.assertRaises(IntegrityError), transaction.atomic():
            SamplingResult.objects.create(batch=batch, material=material, sequence=2)

    def test_result_sequence_is_unique_inside_batch(self):
        first_material = self.create_material("M-001")
        second_material = self.create_material("M-002")
        batch = self.create_batch(version=1)
        SamplingResult.objects.create(batch=batch, material=first_material, sequence=1)

        with self.assertRaises(IntegrityError), transaction.atomic():
            SamplingResult.objects.create(batch=batch, material=second_material, sequence=1)

    def create_material(self, material_number):
        return CandidateMaterial.objects.create(
            task=self.task,
            material_number=material_number,
            order_number="O-1",
            supplier="供应商",
            material_name="物资",
            quantity=10,
        )

    def create_batch(self, version):
        return SamplingBatch.objects.create(
            task=self.task,
            version=version,
            kind=SamplingBatch.Kind.INITIAL,
            status=SamplingBatch.Status.AUTHORIZED,
        )
