import threading
from unittest.mock import patch

from django.db import close_old_connections, connection, transaction
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
        lock_held = threading.Event()
        second_started = threading.Event()
        outcomes = {}
        outcomes_lock = threading.Lock()

        def record_outcome(worker, outcome):
            with outcomes_lock:
                outcomes[worker] = outcome

        def first_attempt():
            close_old_connections()
            try:
                with transaction.atomic():
                    SamplingTask.objects.select_for_update().get(pk=task.id)
                    lock_held.set()
                    if not second_started.wait(timeout=5):
                        raise AssertionError("second worker did not start assignment")
                    with patch(
                        "sampling.services.assignment.secrets.choice",
                        return_value=sampler.id,
                    ):
                        assignment = assign_sampler(task_id=task.id, actor=admin)
                outcome = ("success", assignment.id)
            except ValueError as error:
                outcome = ("state_error", str(error))
            except BaseException as error:
                outcome = ("unexpected_error", repr(error))
            finally:
                close_old_connections()
            record_outcome("first", outcome)

        def second_attempt():
            close_old_connections()
            try:
                if not lock_held.wait(timeout=5):
                    raise AssertionError("first worker did not acquire the task lock")

                def signal_task_lock_query(execute, sql, params, many, context):
                    if (
                        "sampling_samplingtask" in sql
                        and "FOR UPDATE" in sql.upper()
                    ):
                        second_started.set()
                    return execute(sql, params, many, context)

                with patch(
                    "sampling.services.assignment.secrets.choice", return_value=sampler.id
                ), connection.execute_wrapper(signal_task_lock_query):
                    assignment = assign_sampler(task_id=task.id, actor=admin)
                outcome = ("success", assignment.id)
            except ValueError as error:
                outcome = ("state_error", str(error))
            except BaseException as error:
                outcome = ("unexpected_error", repr(error))
            finally:
                close_old_connections()
            record_outcome("second", outcome)

        workers = [
            threading.Thread(target=first_attempt),
            threading.Thread(target=second_attempt),
        ]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=10)

        self.assertTrue(all(not worker.is_alive() for worker in workers))
        self.assertEqual(set(outcomes), {"first", "second"})
        self.assertEqual(outcomes["first"][0], "success")
        self.assertEqual(outcomes["second"][0], "state_error")
        self.assertEqual(
            PersonnelAssignment.objects.filter(
                task=task, kind=PersonnelAssignment.Kind.INITIAL
            ).count(),
            1,
        )
        self.assertEqual(PersonnelAssignment.objects.filter(task=task, is_current=True).count(), 1)
        task.refresh_from_db()
        self.assertEqual(task.status, SamplingTask.Status.ASSIGNED)
