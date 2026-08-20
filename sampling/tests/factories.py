from accounts.models import User
from personnel.models import PersonnelGroup

from sampling.models import CandidateMaterial, PersonnelAssignment, SamplingTask


class SamplingFixturesMixin:
    def make_assigned_task(self, draw_count=1, pool_size=3):
        admin = User.objects.create_user("fixture_admin", role=User.Role.ADMIN)
        sampler = User.objects.create_user("fixture_sampler", role=User.Role.SAMPLER)
        group = PersonnelGroup.objects.create(name="fixture_group", created_by=admin)
        group.members.add(sampler)
        task = SamplingTask.objects.create(
            task_number="FIXTURE-1",
            name="测试任务",
            personnel_group=group,
            draw_count=draw_count,
            status=SamplingTask.Status.ASSIGNED,
            created_by=admin,
        )
        materials = [
            CandidateMaterial.objects.create(
                task=task,
                material_number=f"M-{index:03d}",
                order_number="O-1",
                supplier="供应商",
                material_name="物资",
                quantity=10,
            )
            for index in range(1, pool_size + 1)
        ]
        PersonnelAssignment.objects.create(
            task=task,
            candidate_user_ids=[sampler.id],
            selected_user=sampler,
            kind=PersonnelAssignment.Kind.INITIAL,
            is_current=True,
            created_by=admin,
        )
        return task, sampler, materials
