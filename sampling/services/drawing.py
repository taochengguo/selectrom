import secrets

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from accounts.models import User
from audit.services import log_task_event
from sampling.models import PersonnelAssignment, SamplingBatch, SamplingResult, SamplingTask


def _lock_task(task_id):
    return SamplingTask.objects.select_for_update().get(pk=task_id)


def _current_assignment(task):
    assignments = list(
        task.personnel_assignments.select_for_update().filter(is_current=True).order_by("id")
    )
    if len(assignments) != 1:
        raise ValueError("任务当前分配记录异常")
    return assignments[0]


def _require_current_sampler(task, actor):
    assignment = _current_assignment(task)
    if assignment.selected_user_id != actor.id:
        raise ValueError("仅当前抽样人员可以执行此操作")
    return assignment


def _candidate_ids(task):
    candidate_ids = list(task.candidates.order_by("id").values_list("id", flat=True))
    if len(candidate_ids) < task.draw_count:
        raise ValueError("候选物资数量不足")
    return candidate_ids


def _lock_batch_with_results(*, task, batch, actor, event_type):
    if batch.results.exists():
        raise ValueError("授权重抽批次必须为空")

    selected_material_ids = secrets.SystemRandom().sample(
        _candidate_ids(task), task.draw_count
    )
    SamplingResult.objects.bulk_create(
        [
            SamplingResult(batch=batch, material_id=material_id, sequence=sequence)
            for sequence, material_id in enumerate(selected_material_ids, start=1)
        ]
    )
    drawn_at = timezone.now()
    batch.status = SamplingBatch.Status.LOCKED
    batch.drawn_by = actor
    batch.drawn_at = drawn_at
    batch.save(update_fields=["status", "drawn_by", "drawn_at"])
    task.status = SamplingTask.Status.IN_PROGRESS
    task.save(update_fields=["status", "updated_at"])
    log_task_event(
        task=task,
        actor=actor,
        event_type=event_type,
        before={"status": SamplingTask.Status.ASSIGNED, "batch_id": batch.id},
        after={
            "status": SamplingTask.Status.IN_PROGRESS,
            "batch_id": batch.id,
            "version": batch.version,
            "material_ids": selected_material_ids,
        },
    )
    return batch


@transaction.atomic
def draw_materials(*, task_id: int, actor) -> SamplingBatch:
    task = _lock_task(task_id)
    _require_current_sampler(task, actor)

    authorized_redraw = (
        task.sampling_batches.select_for_update()
        .filter(kind=SamplingBatch.Kind.REDRAW, status=SamplingBatch.Status.AUTHORIZED)
        .order_by("version")
        .first()
    )
    if authorized_redraw:
        if task.status != SamplingTask.Status.ASSIGNED:
            raise ValueError("任务当前状态不可执行")
        return _lock_batch_with_results(
            task=task,
            batch=authorized_redraw,
            actor=actor,
            event_type="draw.redraw",
        )

    latest_locked_batch = (
        task.sampling_batches.select_for_update()
        .filter(status=SamplingBatch.Status.LOCKED)
        .order_by("-version")
        .first()
    )
    if latest_locked_batch:
        return latest_locked_batch

    if task.sampling_batches.filter(kind=SamplingBatch.Kind.INITIAL).exists():
        raise ValueError("首次抽样批次状态异常")
    if task.status != SamplingTask.Status.ASSIGNED:
        raise ValueError("未授权重抽")

    batch = SamplingBatch.objects.create(
        task=task,
        version=1,
        kind=SamplingBatch.Kind.INITIAL,
        status=SamplingBatch.Status.AUTHORIZED,
    )
    return _lock_batch_with_results(
        task=task,
        batch=batch,
        actor=actor,
        event_type="draw.initial",
    )


@transaction.atomic
def authorize_redraw(*, task_id: int, actor, reason: str) -> SamplingBatch:
    reason = reason.strip()
    if not reason:
        raise ValueError("重抽原因不能为空")
    if actor.role != User.Role.ADMIN:
        raise ValueError("仅管理员可以授权重抽")

    task = _lock_task(task_id)
    if task.status not in {SamplingTask.Status.IN_PROGRESS, SamplingTask.Status.COMPLETED}:
        raise ValueError("任务当前状态不可执行")
    if task.sampling_batches.filter(status=SamplingBatch.Status.AUTHORIZED).exists():
        raise ValueError("已有待执行的重抽批次")

    latest_version = task.sampling_batches.aggregate(max_version=Max("version"))["max_version"] or 0
    batch = SamplingBatch.objects.create(
        task=task,
        version=latest_version + 1,
        kind=SamplingBatch.Kind.REDRAW,
        status=SamplingBatch.Status.AUTHORIZED,
        reason=reason,
        approved_by=actor,
        approved_at=timezone.now(),
    )
    before_status = task.status
    task.status = SamplingTask.Status.ASSIGNED
    task.save(update_fields=["status", "updated_at"])
    log_task_event(
        task=task,
        actor=actor,
        event_type="draw.redraw_authorized",
        before={"status": before_status},
        after={
            "status": SamplingTask.Status.ASSIGNED,
            "batch_id": batch.id,
            "version": batch.version,
            "reason": reason,
        },
    )
    return batch


@transaction.atomic
def complete_task(*, task_id: int, actor) -> SamplingTask:
    task = _lock_task(task_id)
    _require_current_sampler(task, actor)
    if task.status == SamplingTask.Status.COMPLETED:
        return task
    if task.status != SamplingTask.Status.IN_PROGRESS:
        raise ValueError("任务当前状态不可执行")

    latest_batch = (
        task.sampling_batches.select_for_update()
        .filter(status=SamplingBatch.Status.LOCKED)
        .order_by("-version")
        .first()
    )
    if latest_batch is None:
        raise ValueError("任务没有锁定的抽样批次")

    task.status = SamplingTask.Status.COMPLETED
    task.save(update_fields=["status", "updated_at"])
    log_task_event(
        task=task,
        actor=actor,
        event_type="task.completed",
        before={"status": SamplingTask.Status.IN_PROGRESS},
        after={
            "status": SamplingTask.Status.COMPLETED,
            "batch_id": latest_batch.id,
            "version": latest_batch.version,
        },
    )
    return task
