from django.core.management import call_command
from django.test import TestCase

from accounts.models import User
from personnel.models import PersonnelGroup
from sampling.models import CandidateMaterial, SamplingTask


class SeedDemoTests(TestCase):
    def test_seed_demo_is_idempotent(self):
        call_command("seed_demo")
        call_command("seed_demo")

        self.assertEqual(User.objects.filter(username="demo_admin").count(), 1)
        self.assertEqual(User.objects.filter(role=User.Role.SAMPLER).count(), 3)
        group = PersonnelGroup.objects.get(name="演示抽样组")
        self.assertEqual(group.members.count(), 3)
        self.assertEqual(SamplingTask.objects.filter(task_number="DEMO-DRAFT-001").count(), 1)
        self.assertEqual(SamplingTask.objects.filter(task_number="DEMO-READY-001").count(), 1)
        self.assertEqual(
            CandidateMaterial.objects.filter(task__task_number="DEMO-READY-001").count(),
            10,
        )
