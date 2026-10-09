from django.db import transaction
from django.utils import timezone
from uuid import uuid4

from audit.services import log_task_event
from sampling.models import CandidateMaterial, SamplingTask


class TaskFrozenError(ValueError):
    """Raised when an executed task is changed in a protected way."""


_MUTABLE_TASK_STATUSES = {SamplingTask.Status.DRAFT, SamplingTask.Status.READY}
_CANCELLABLE_TASK_STATUSES = {
    SamplingTask.Status.DRAFT,
    SamplingTask.Status.READY,
    SamplingTask.Status.ASSIGNED,
    SamplingTask.Status.IN_PROGRESS,
    SamplingTask.Status.COMPLETED,
}
_TASK_FIELDS = {
    "task_number",
    "name",
    "personnel_group",
    "planned_at",
    "draw_count",
    "notes",
    "sample_mode", "sample_quantity", "inspection_type", "purchase_order_number",
    "order_line_id", "planned_inspection_date", "receiving_unit", "supplier_name",
    "material_code", "material_name", "specification", "contact_name",
    "receiver_phone", "delivery_address",
}
_UNIT_FIELDS = {
    "inspection_type", "purchase_order_number", "order_line_id",
    "planned_inspection_date", "receiving_unit", "supplier_name",
    "material_code", "material_name", "specification", "contact_name",
    "receiver_phone", "delivery_address", "personnel_group",
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
        "sample_mode": task.sample_mode,
        "sample_quantity": task.sample_quantity,
        "inspection_type": task.inspection_type,
        "purchase_order_number": task.purchase_order_number,
        "order_line_id": task.order_line_id,
        "planned_inspection_date": task.planned_inspection_date.isoformat() if task.planned_inspection_date else None,
        "receiving_unit": task.receiving_unit,
        "supplier_name": task.supplier_name,
        "material_code": task.material_code,
        "material_name": task.material_name,
        "specification": task.specification,
        "contact_name": task.contact_name,
        "receiver_phone": task.receiver_phone,
        "delivery_address": task.delivery_address,
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
    # Candidate IDs are the frozen draw pool once a task has been assigned.
    if task.sample_mode == SamplingTask.SampleMode.UNIT:
        raise TaskFrozenError("样品序号抽样任务不使用候选物资")
    if task.status not in _MUTABLE_TASK_STATUSES:
        raise TaskFrozenError("任务已执行，候选物资不可修改")


def _ensure_task_fields_mutable(task, changes):
    protected_fields = {"personnel_group", "draw_count"}
    if task.sample_mode == SamplingTask.SampleMode.UNIT:
        protected_fields |= _UNIT_FIELDS | {"sample_quantity", "name", "sample_mode"}
    if task.status not in _MUTABLE_TASK_STATUSES and protected_fields.intersection(changes):
        if task.sample_mode == SamplingTask.SampleMode.UNIT:
            raise TaskFrozenError("任务已执行，抽样信息不可修改")
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


def create_unit_task(*, actor, **values):
    _validate_fields(values, _UNIT_FIELDS)
    return create_task(
        actor=actor,
        task_number=f"S-{timezone.localdate():%Y%m%d}-{uuid4().hex[:10].upper()}",
        name=values["material_name"],
        sample_mode=SamplingTask.SampleMode.UNIT,
        **values,
    )


def update_task(*, task_id, actor, **changes):
    _validate_fields(changes, _TASK_FIELDS)
    with transaction.atomic():
        task = _lock_task(task_id)
        _ensure_task_fields_mutable(task, changes)
        before = _task_data(task)
        for field, value in changes.items():
            setattr(task, field, value)
        if {"receiving_unit", "delivery_address"}.intersection(changes):
            task.site_longitude = None
            task.site_latitude = None
            task.site_geocoded_at = None
            task.site_city = ""
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
        if task.status == SamplingTask.Status.READY:
            return task
        if task.status != SamplingTask.Status.DRAFT:
            raise TaskFrozenError("任务已执行，不能改回待执行状态")
        before = _task_data(task)
        if task.sample_mode == SamplingTask.SampleMode.MATERIAL:
            candidate_count = task.candidates.count()
            if not task.draw_count or task.draw_count <= 0:
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
        if task.status == SamplingTask.Status.CANCELLED:
            return task
        if task.status not in _CANCELLABLE_TASK_STATUSES:
            raise ValueError("任务当前状态不可取消")
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
