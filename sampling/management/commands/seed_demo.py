from django.core.management.base import BaseCommand

from accounts.models import User
from personnel.models import PersonnelGroup
from sampling.models import CandidateMaterial, SamplingTask


DEMO_PASSWORD = "demo123456"
DEMO_SAMPLERS = (
    ("demo_sampler_01", "演示抽样员一"),
    ("demo_sampler_02", "演示抽样员二"),
    ("demo_sampler_03", "演示抽样员三"),
)
DEMO_MATERIALS = (
    ("DEMO-M-001", "DEMO-O-001", "华北演示供应商", "演示物资 01", 100),
    ("DEMO-M-002", "DEMO-O-002", "华北演示供应商", "演示物资 02", 120),
    ("DEMO-M-003", "DEMO-O-003", "华东演示供应商", "演示物资 03", 80),
    ("DEMO-M-004", "DEMO-O-004", "华东演示供应商", "演示物资 04", 90),
    ("DEMO-M-005", "DEMO-O-005", "华南演示供应商", "演示物资 05", 150),
    ("DEMO-M-006", "DEMO-O-006", "华南演示供应商", "演示物资 06", 60),
    ("DEMO-M-007", "DEMO-O-007", "西部演示供应商", "演示物资 07", 75),
    ("DEMO-M-008", "DEMO-O-008", "西部演示供应商", "演示物资 08", 110),
    ("DEMO-M-009", "DEMO-O-009", "北方演示供应商", "演示物资 09", 95),
    ("DEMO-M-010", "DEMO-O-010", "北方演示供应商", "演示物资 10", 130),
)


class Command(BaseCommand):
    help = "创建或更新本机随机抽样演示数据。"

    def handle(self, *args, **options):
        admin, _ = User.objects.update_or_create(
            username="demo_admin",
            defaults={
                "role": User.Role.ADMIN,
                "first_name": "演示管理员",
                "is_active": True,
            },
        )
        admin.set_password(DEMO_PASSWORD)
        admin.save(update_fields=["password"])

        samplers = []
        for username, first_name in DEMO_SAMPLERS:
            sampler, _ = User.objects.update_or_create(
                username=username,
                defaults={
                    "role": User.Role.SAMPLER,
                    "first_name": first_name,
                    "is_active": True,
                },
            )
            sampler.set_password(DEMO_PASSWORD)
            sampler.save(update_fields=["password"])
            samplers.append(sampler)

        group, _ = PersonnelGroup.objects.update_or_create(
            name="演示抽样组",
            defaults={
                "description": "仅用于本机演示的抽样人员分组",
                "created_by": admin,
            },
        )
        group.members.set(samplers)

        SamplingTask.objects.update_or_create(
            task_number="DEMO-DRAFT-001",
            defaults={
                "name": "演示草稿抽样任务",
                "personnel_group": group,
                "draw_count": 3,
                "status": SamplingTask.Status.DRAFT,
                "notes": "可在后台继续编辑或导入候选物资。",
                "created_by": admin,
            },
        )
        ready_task, _ = SamplingTask.objects.update_or_create(
            task_number="DEMO-READY-001",
            defaults={
                "name": "演示待执行抽样任务",
                "personnel_group": group,
                "draw_count": 3,
                "status": SamplingTask.Status.READY,
                "notes": "可在后台执行，系统会随机分配一名抽样人员。",
                "created_by": admin,
            },
        )
        for material_number, order_number, supplier, material_name, quantity in DEMO_MATERIALS:
            CandidateMaterial.objects.update_or_create(
                task=ready_task,
                material_number=material_number,
                defaults={
                    "order_number": order_number,
                    "supplier": supplier,
                    "material_name": material_name,
                    "quantity": quantity,
                },
            )

        self.stdout.write(self.style.SUCCESS("本机演示数据已准备完成。"))
        self.stdout.write("管理员：demo_admin")
        self.stdout.write("抽样人员：demo_sampler_01、demo_sampler_02、demo_sampler_03")
        self.stdout.write(
            self.style.WARNING("仅本机演示密码：demo123456；非演示环境必须修改密码。")
        )
