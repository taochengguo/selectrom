from django.test import TestCase
from django.urls import reverse
from accounts.models import User
from personnel.models import PersonnelGroup
from sampling.models import SamplingTask
from sampling.forms import UnitSamplingTaskForm
from sampling.services.lifecycle import mark_task_ready
from sampling.services.assignment import assign_sampler
from sampling.services.drawing import draw_materials


class TaskPresetTests(TestCase):
    def setUp(self):
        self.admin=User.objects.create_user('preset_admin',role='admin')
        self.sampler=User.objects.create_user('preset_sampler',role='sampler')
        self.group=PersonnelGroup.objects.create(name='预设组',created_by=self.admin)
        self.group.members.add(self.sampler)
        self.client.force_login(self.admin)

    def test_only_purchase_order_required(self):
        form=UnitSamplingTaskForm()
        self.assertEqual(next(iter(form.fields)),'purchase_order_number')
        self.assertEqual([key for key,field in form.fields.items() if field.required],['purchase_order_number'])
        response=self.client.post(reverse('management:task-create'),{'mode':'unit','purchase_order_number':'PO-ONLY'})
        self.assertEqual(response.status_code,302)
        task=SamplingTask.objects.get(purchase_order_number='PO-ONLY')
        self.assertIsNone(task.personnel_group_id)
        self.assertEqual(task.name,'PO-ONLY')
        mark_task_ready(task_id=task.pk,actor=self.admin)
        with self.assertRaisesMessage(ValueError,'请先选择抽样人员分组'):
            assign_sampler(task_id=task.pk,actor=self.admin)

    def test_counts_prefilled_corrected_and_then_locked(self):
        response=self.client.post(reverse('management:task-create'),{'mode':'unit','purchase_order_number':'PO-PRESET','personnel_group':self.group.pk,'detailed_address':'三号库房','sample_quantity':30,'draw_count':5})
        self.assertEqual(response.status_code,302)
        task=SamplingTask.objects.get(purchase_order_number='PO-PRESET')
        self.assertEqual((task.sample_quantity,task.draw_count,task.detailed_address),(30,5,'三号库房'))
        mark_task_ready(task_id=task.pk,actor=self.admin)
        assign_sampler(task_id=task.pk,actor=self.admin)
        self.client.force_login(self.sampler)
        response=self.client.get(reverse('mobile:task-detail',args=[task.pk]))
        self.assertContains(response,'name="sample_quantity" value="30"')
        self.assertContains(response,'name="draw_count" value="5"')
        batch=draw_materials(task_id=task.pk,actor=self.sampler,sample_quantity=20,draw_count=3)
        task.refresh_from_db()
        self.assertEqual((task.sample_quantity,task.draw_count),(20,3))
        self.assertEqual(batch.results.count(),3)
        draw_materials(task_id=task.pk,actor=self.sampler,sample_quantity=99,draw_count=2)
        task.refresh_from_db()
        self.assertEqual((task.sample_quantity,task.draw_count),(20,3))

    def test_invalid_counts_rejected(self):
        for extra in ({'sample_quantity':0},{'draw_count':10001},{'sample_quantity':2,'draw_count':3}):
            form=UnitSamplingTaskForm({'purchase_order_number':'PO',**extra})
            self.assertFalse(form.is_valid())
