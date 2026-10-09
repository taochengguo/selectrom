from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from personnel.models import PersonnelGroup
from sampling.models import PersonnelAssignment, SamplingTask
from sampling.services.assignment import assign_sampler
from sampling.services.drawing import authorize_redraw
from sampling.services.lifecycle import mark_task_ready


class UnitSamplingFlowTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("unit_admin", role=User.Role.ADMIN)
        self.sampler = User.objects.create_user("unit_sampler", role=User.Role.SAMPLER)
        self.group = PersonnelGroup.objects.create(name="单位抽样组", created_by=self.admin)
        self.group.members.add(self.sampler)

    def test_admin_creates_unit_task_from_dialog_without_counts(self):
        self.client.force_login(self.admin)
        listing = self.client.get(reverse("management:task-list"))
        self.assertContains(listing, 'id="task-create-dialog"')
        response = self.client.post(reverse("management:task-create"), {
            "mode": "unit", "personnel_group": self.group.pk,
            "inspection_type": "到货质检", "purchase_order_number": "PO-100",
            "order_line_id": "10", "planned_inspection_date": "2026-10-01",
            "receiving_unit": "收货单位", "supplier_name": "供应商甲",
            "material_code": "MAT-1", "material_name": "螺栓",
            "specification": "M12", "contact_name": "张三",
            "receiver_phone": "13800138000", "delivery_address": "上海市测试路1号",
        })
        self.assertEqual(response.status_code, 302)
        task = SamplingTask.objects.get(purchase_order_number="PO-100")
        self.assertEqual(task.sample_mode, SamplingTask.SampleMode.UNIT)
        self.assertIsNone(task.sample_quantity)
        self.assertIsNone(task.draw_count)
        self.assertEqual(task.order_line_id, "10")
        self.assertContains(self.client.get(reverse("management:task-detail", args=[task.pk])), "上海市测试路1号")
        mark_task_ready(task_id=task.pk, actor=self.admin)
        assignment = assign_sampler(task_id=task.pk, actor=self.admin)
        self.assertEqual(assignment.selected_user, self.sampler)

    def test_sampler_enters_counts_then_draws_unique_unit_numbers(self):
        task = SamplingTask.objects.create(
            task_number="UNIT-1", name="螺栓", personnel_group=self.group,
            sample_mode=SamplingTask.SampleMode.UNIT,
            draw_count=None, status=SamplingTask.Status.ASSIGNED,
            created_by=self.admin,
        )
        PersonnelAssignment.objects.create(
            task=task, candidate_user_ids=[self.sampler.pk],
            selected_user=self.sampler, kind=PersonnelAssignment.Kind.INITIAL,
            is_current=True, created_by=self.admin,
        )
        self.client.force_login(self.sampler)
        detail = self.client.get(reverse("mobile:task-detail", args=[task.pk]))
        self.assertContains(detail, 'name="sample_quantity"')
        self.assertContains(detail, 'name="draw_count"')
        bad = self.client.post(reverse("mobile:task-draw", args=[task.pk]), {
            "sample_quantity": "3", "draw_count": "4",
        })
        self.assertEqual(bad.status_code, 400)
        task.refresh_from_db()
        self.assertIsNone(task.sample_quantity)
        good = self.client.post(reverse("mobile:task-draw", args=[task.pk]), {
            "sample_quantity": "30", "draw_count": "5",
        })
        self.assertEqual(good.status_code, 200)
        numbers = [item["sample_number"] for item in good.json()["results"]]
        self.assertEqual(len(numbers), 5)
        self.assertEqual(len(set(numbers)), 5)
        self.assertTrue(all(1 <= number <= 30 for number in numbers))
        task.refresh_from_db()
        self.assertEqual((task.sample_quantity, task.draw_count), (30, 5))
        self.client.force_login(self.admin)
        listing = self.client.get(reverse("management:task-list"))
        self.assertContains(listing, "30")
        self.assertContains(listing, "5")
        self.client.force_login(self.sampler)
        repeated = self.client.post(reverse("mobile:task-draw", args=[task.pk]), {
            "sample_quantity": "99", "draw_count": "1",
        })
        self.assertEqual(repeated.json(), good.json())
        task.refresh_from_db()
        self.assertEqual((task.sample_quantity, task.draw_count), (30, 5))

        authorize_redraw(task_id=task.pk, actor=self.admin, reason="复核")
        redraw = self.client.post(reverse("mobile:task-draw", args=[task.pk]))
        self.assertEqual(redraw.status_code, 200)
        redraw_numbers = [item["sample_number"] for item in redraw.json()["results"]]
        self.assertEqual(len(redraw_numbers), 5)
        self.assertEqual(len(set(redraw_numbers)), 5)
        self.assertEqual(redraw.json()["batch_version"], 2)

    def test_missing_required_task_information_keeps_dialog_open(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("management:task-create"), {
            "mode": "unit", "personnel_group": self.group.pk,
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["open_dialog"])
        self.assertContains(response, "新建抽样任务")
        self.assertFalse(SamplingTask.objects.filter(sample_mode=SamplingTask.SampleMode.UNIT).exists())
