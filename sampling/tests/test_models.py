from django.db import IntegrityError, transaction
from django.test import TestCase

from accounts.models import User
from personnel.models import PersonnelGroup
from sampling.models import CandidateMaterial, SamplingTask


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

    def test_task_cannot_be_ready_when_draw_count_exceeds_pool(self):
        with self.assertRaisesMessage(ValueError, "抽取数量不能超过候选物资数量"):
            self.task.mark_ready()
