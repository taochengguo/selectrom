import threading

from django.db import close_old_connections, connection, transaction
from django.test import TransactionTestCase

from accounts.models import User
from personnel.models import PersonnelGroup
from sampling.models import (
    CandidateMaterial,
    PersonnelAssignment,
    SamplingBatch,
    SamplingResult,
    SamplingTask,
)
from sampling.services.drawing import draw_materials


class DrawingConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def test_two_draw_attempts_create_one_locked_initial_batch_on_mysql(self):
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
            draw_count=2,
            status=SamplingTask.Status.ASSIGNED,
            created_by=admin,
        )
        for number in range(1, 4):
            CandidateMaterial.objects.create(
                task=task,
                material_number=f"M-{number}",
                order_number="O-1",
                supplier="供应商",
                material_name="物资",
                quantity=10,
            )
        PersonnelAssignment.objects.create(
            task=task,
            candidate_user_ids=[sampler.id],
            selected_user=sampler,
            kind=PersonnelAssignment.Kind.INITIAL,
            is_current=True,
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
                        raise AssertionError("second worker did not start its locked draw")
                    batch = draw_materials(task_id=task.id, actor=sampler)
                outcome = ("success", batch.id)
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
                    if "sampling_samplingtask" in sql and "FOR UPDATE" in sql.upper():
                        second_started.set()
                    return execute(sql, params, many, context)

                with connection.execute_wrapper(signal_task_lock_query):
                    batch = draw_materials(task_id=task.id, actor=sampler)
                outcome = ("success", batch.id)
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
        self.assertEqual(outcomes["second"][0], "success")
        self.assertEqual(outcomes["first"][1], outcomes["second"][1])
        batch = SamplingBatch.objects.get(task=task, kind=SamplingBatch.Kind.INITIAL)
        self.assertEqual(batch.status, SamplingBatch.Status.LOCKED)
        self.assertEqual(SamplingBatch.objects.filter(task=task).count(), 1)
        self.assertEqual(SamplingResult.objects.filter(batch=batch).count(), task.draw_count)
