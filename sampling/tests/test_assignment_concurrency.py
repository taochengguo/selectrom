import threading
from unittest.mock import patch

from django.db import close_old_connections, connection
from django.test import TransactionTestCase

from accounts.models import User
from personnel.models import PersonnelGroup
from sampling.models import PersonnelAssignment, SamplingTask
from sampling.services.assignment import assign_sampler


class AssignmentConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def test_two_initial_assignment_attempts_create_only_one_record_on_mysql(self):
        if connection.vendor != "mysql":
            self.skipTest("requires MySQL row locking")

        admin = User.objects.create_user("admin", role=User.Role.ADMIN)
        sampler = User.objects.create_user("sampler", role=User.Role.SAMPLER)
        group = PersonnelGroup.objects.create(name="第一组", created_by=admin)
        group.members.add(sampler)
        task = SamplingTask.objects.create(
            task_number="T-1",
            name="任务",
            personnel_group=group,
            draw_count=1,
            status=SamplingTask.Status.READY,
            created_by=admin,
        )
        start = threading.Barrier(2)
        outcomes = []
        outcomes_lock = threading.Lock()

        def attempt_assignment():
            close_old_connections()
            try:
                start.wait()
                with patch("sampling.services.assignment.secrets.choice", return_value=sampler.id):
                    assignment = assign_sampler(task_id=task.id, actor=admin)
                outcome = ("success", assignment.id)
            except ValueError as error:
                outcome = ("state_error", str(error))
            finally:
                close_old_connections()
            with outcomes_lock:
                outcomes.append(outcome)

        workers = [threading.Thread(target=attempt_assignment) for _ in range(2)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=10)

        self.assertTrue(all(not worker.is_alive() for worker in workers))
        self.assertEqual(sorted(outcome[0] for outcome in outcomes), ["state_error", "success"])
        self.assertEqual(
            PersonnelAssignment.objects.filter(
                task=task, kind=PersonnelAssignment.Kind.INITIAL
            ).count(),
            1,
        )
