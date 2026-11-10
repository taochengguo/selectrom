from django.test import TestCase
from django.urls import reverse
from accounts.models import User
from audit.models import TaskAuditLog
from personnel.models import PersonnelGroup
from sampling.tests.factories import SamplingFixturesMixin
from sampling.services.assignment import reassign_sampler


class ReassignGroupTests(SamplingFixturesMixin, TestCase):
    def setUp(self):
        self.task,self.sampler,_=self.make_assigned_task()
        self.admin=self.task.created_by
        self.original=self.task.personnel_assignments.get(is_current=True)
        self.other=User.objects.create_user('new_sampler',role='sampler',first_name='新组员')
        self.new_group=PersonnelGroup.objects.create(name='新分组',created_by=self.admin)
        self.new_group.members.add(self.other)

    def test_reassign_changes_group_and_logs_before_after(self):
        old_group=self.task.personnel_group_id
        self.client.force_login(self.admin)
        response=self.client.post(reverse('management:task-reassign',args=[self.task.pk]),{'personnel_group':self.new_group.pk,'reason':'调整现场人员'})
        self.assertEqual(response.status_code,302)
        self.task.refresh_from_db()
        self.original.refresh_from_db()
        self.assertEqual(self.task.personnel_group_id,self.new_group.pk)
        self.assertFalse(self.original.is_current)
        assignment=self.task.personnel_assignments.get(is_current=True)
        self.assertEqual(assignment.selected_user,self.other)
        self.assertEqual(assignment.candidate_user_ids,[self.other.pk])
        log=TaskAuditLog.objects.get(task=self.task,event_type='assignment.reassigned')
        self.assertEqual(log.before_data['personnel_group_id'],old_group)
        self.assertEqual(log.after_data['personnel_group_id'],self.new_group.pk)

    def test_invalid_or_empty_group_leaves_original_assignment(self):
        empty=PersonnelGroup.objects.create(name='空组',created_by=self.admin)
        old_group=self.task.personnel_group_id
        for group_id in (empty.pk,999999,'invalid'):
            with self.assertRaises(ValueError):
                reassign_sampler(task_id=self.task.pk,actor=self.admin,reason='调整',personnel_group_id=group_id)
            self.task.refresh_from_db()
            self.original.refresh_from_db()
            self.assertEqual(self.task.personnel_group_id,old_group)
            self.assertTrue(self.original.is_current)
        self.assertEqual(self.task.personnel_assignments.count(),1)
        self.assertFalse(TaskAuditLog.objects.filter(task=self.task,event_type='assignment.reassigned').exists())
