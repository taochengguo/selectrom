from audit.models import TaskAuditLog


def log_task_event(*, task, actor, event_type, before=None, after=None, ip_address=None):
    return TaskAuditLog.objects.create(
        task=task,
        actor=actor,
        event_type=event_type,
        before_data=before or {},
        after_data=after or {},
        ip_address=ip_address,
    )
