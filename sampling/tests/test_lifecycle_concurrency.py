import threading

from django.db import close_old_connections, connection
from django.test import TransactionTestCase

from accounts.models import User
from audit.models import TaskAuditLog
from personnel.models import PersonnelGroup
from sampling.models import SamplingTask
from sampling.services.lifecycle import cancel_task


class LifecycleConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def test_concurrent_cancel_attempts_create_one_audit_event_on_mysql(self):
        if connection.vendor != "mysql":
            self.skipTest("requires MySQL row locking")

        admin = User.objects.create_user("admin", role=User.Role.ADMIN)
        group = PersonnelGroup.objects.create(name="cancel_group", created_by=admin)
        task = SamplingTask.objects.create(
            task_number="CANCEL-RACE",
            name="cancel race",
            personnel_group=group,
            draw_count=1,
            status=SamplingTask.Status.DRAFT,
            created_by=admin,
        )
        start = threading.Barrier(2)
        outcomes = []
        outcomes_lock = threading.Lock()

        def cancel_once():
            close_old_connections()
            try:
                start.wait(timeout=5)
                cancelled = cancel_task(task_id=task.id, actor=admin)
                outcome = ("success", cancelled.id)
            except BaseException as error:
                outcome = ("error", repr(error))
            finally:
                close_old_connections()
            with outcomes_lock:
                outcomes.append(outcome)

        workers = [threading.Thread(target=cancel_once) for _ in range(2)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=10)

        self.assertTrue(all(not worker.is_alive() for worker in workers))
        self.assertEqual(len(outcomes), 2)
        self.assertEqual({outcome[0] for outcome in outcomes}, {"success"})
        self.assertEqual({outcome[1] for outcome in outcomes}, {task.id})
        self.assertEqual(
            TaskAuditLog.objects.filter(
                task=task, event_type="task.cancelled"
            ).count(),
            1,
        )
        task.refresh_from_db()
        self.assertEqual(task.status, SamplingTask.Status.CANCELLED)
