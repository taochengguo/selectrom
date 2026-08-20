from django.db import transaction

from audit.services import log_task_event
from sampling.models import CandidateMaterial, SamplingTask


class TaskFrozenError(ValueError):
    """Raised when an executed task is changed in a protected way."""


_MUTABLE_TASK_STATUSES = {SamplingTask.Status.DRAFT, SamplingTask.Status.READY}
_TASK_FIELDS = {
    "task_number",
    "name",
    "personnel_group",
    "planned_at",
    "draw_count",
    "notes",
}
_CANDIDATE_FIELDS = {
    "material_number",
    "order_number",
    "supplier",
    "material_name",
    "quantity",
}


def _lock_task(task_id):
    return SamplingTask.objects.select_for_update().get(pk=task_id)


def _task_data(task):
    return {
        "task_number": task.task_number,
        "name": task.name,
        "personnel_group_id": task.personnel_group_id,
        "planned_at": task.planned_at.isoformat() if task.planned_at else None,
        "draw_count": task.draw_count,
        "status": task.status,
        "notes": task.notes,
    }


def _candidate_data(candidate):
    return {
        "id": candidate.id,
        "material_number": candidate.material_number,
        "order_number": candidate.order_number,
        "supplier": candidate.supplier,
        "material_name": candidate.material_name,
        "quantity": candidate.quantity,
    }


def _ensure_candidate_mutable(task):
    if task.status not in _MUTABLE_TASK_STATUSES:
        raise TaskFrozenError("任务已执行，候选物资不可修改")


def _ensure_task_fields_mutable(task, changes):
    protected_fields = {"personnel_group", "draw_count"}
    if task.status not in _MUTABLE_TASK_STATUSES and protected_fields.intersection(changes):
        raise TaskFrozenError("任务已执行，抽样组和抽取数量不可修改")


def _validate_fields(values, allowed_fields):
    unexpected_fields = set(values).difference(allowed_fields)
    if unexpected_fields:
        unexpected = "、".join(sorted(unexpected_fields))
        raise ValueError(f"不支持的字段：{unexpected}")


def create_task(*, actor, **values):
    _validate_fields(values, _TASK_FIELDS)
    with transaction.atomic():
        task = SamplingTask(created_by=actor, **values)
        task.full_clean()
        task.save()
        log_task_event(
            task=task,
            actor=actor,
            event_type="task.created",
            before={},
            after=_task_data(task),
        )
        return task


def update_task(*, task_id, actor, **changes):
    _validate_fields(changes, _TASK_FIELDS)
    with transaction.atomic():
        task = _lock_task(task_id)
        _ensure_task_fields_mutable(task, changes)
        before = _task_data(task)
        for field, value in changes.items():
            setattr(task, field, value)
        task.full_clean()
        task.save()
        log_task_event(
            task=task,
            actor=actor,
            event_type="task.updated",
            before=before,
            after=_task_data(task),
        )
        return task


def mark_task_ready(*, task_id, actor):
    with transaction.atomic():
        task = _lock_task(task_id)
        before = _task_data(task)
        candidate_count = task.candidates.count()
        if task.draw_count <= 0:
            raise ValueError("抽取数量必须大于零")
        if task.draw_count > candidate_count:
            raise ValueError("抽取数量不能超过候选物资数量")
        task.status = SamplingTask.Status.READY
        task.full_clean()
        task.save()
        log_task_event(
            task=task,
            actor=actor,
            event_type="task.ready",
            before=before,
            after=_task_data(task),
        )
        return task


def cancel_task(*, task_id, actor):
    with transaction.atomic():
        task = _lock_task(task_id)
        before = _task_data(task)
        task.status = SamplingTask.Status.CANCELLED
        task.full_clean()
        task.save()
        log_task_event(
            task=task,
            actor=actor,
            event_type="task.cancelled",
            before=before,
            after=_task_data(task),
        )
        return task


def create_candidate(*, task_id, actor, **values):
    _validate_fields(values, _CANDIDATE_FIELDS)
    with transaction.atomic():
        task = _lock_task(task_id)
        _ensure_candidate_mutable(task)
        candidate = CandidateMaterial(task=task, **values)
        candidate.full_clean()
        candidate.save()
        log_task_event(
            task=task,
            actor=actor,
            event_type="material.created",
            before={},
            after=_candidate_data(candidate),
        )
        return candidate


def update_candidate(*, candidate_id, actor, **changes):
    _validate_fields(changes, _CANDIDATE_FIELDS)
    with transaction.atomic():
        candidate = CandidateMaterial.objects.select_for_update().get(pk=candidate_id)
        task = _lock_task(candidate.task_id)
        _ensure_candidate_mutable(task)
        before = _candidate_data(candidate)
        for field, value in changes.items():
            setattr(candidate, field, value)
        candidate.full_clean()
        candidate.save()
        log_task_event(
            task=task,
            actor=actor,
            event_type="material.updated",
            before=before,
            after=_candidate_data(candidate),
        )
        return candidate


def delete_candidate(*, candidate_id, actor):
    with transaction.atomic():
        candidate = CandidateMaterial.objects.select_for_update().get(pk=candidate_id)
        task = _lock_task(candidate.task_id)
        _ensure_candidate_mutable(task)
        before = _candidate_data(candidate)
        candidate.delete()
        log_task_event(
            task=task,
            actor=actor,
            event_type="material.deleted",
            before=before,
            after={},
        )
