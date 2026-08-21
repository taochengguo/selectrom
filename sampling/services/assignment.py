import secrets

from django.db import transaction

from audit.services import log_task_event
from sampling.models import PersonnelAssignment, SamplingBatch, SamplingTask


def _candidate_user_ids(task):
    return list(
        task.personnel_group.members.order_by("id").values_list("id", flat=True)
    )


def _require_candidates(task):
    candidate_user_ids = _candidate_user_ids(task)
    if not candidate_user_ids:
        raise ValueError("抽样人员分组不能为空")
    return candidate_user_ids


@transaction.atomic
def assign_sampler(*, task_id: int, actor):
    task = (
        SamplingTask.objects.select_for_update()
        .select_related("personnel_group")
        .get(pk=task_id)
    )
    if task.status != SamplingTask.Status.READY:
        raise ValueError("任务当前状态不可执行")
    if task.personnel_assignments.filter(kind=PersonnelAssignment.Kind.INITIAL).exists():
        raise ValueError("任务当前状态不可执行")

    candidate_user_ids = _require_candidates(task)
    selected_user_id = secrets.choice(candidate_user_ids)
    assignment = PersonnelAssignment.objects.create(
        task=task,
        candidate_user_ids=candidate_user_ids,
        selected_user_id=selected_user_id,
        kind=PersonnelAssignment.Kind.INITIAL,
        is_current=True,
        created_by=actor,
    )
    task.status = SamplingTask.Status.ASSIGNED
    task.save(update_fields=["status", "updated_at"])
    log_task_event(
        task=task,
        actor=actor,
        event_type="assignment.initial",
        before={"status": SamplingTask.Status.READY},
        after={
            "status": SamplingTask.Status.ASSIGNED,
            "assignment_id": assignment.id,
            "candidate_user_ids": candidate_user_ids,
            "selected_user_id": selected_user_id,
        },
    )
    return assignment


@transaction.atomic
def reassign_sampler(*, task_id: int, actor, reason: str):
    reason = reason.strip()
    if not reason:
        raise ValueError("重分配原因不能为空")

    task = (
        SamplingTask.objects.select_for_update()
        .select_related("personnel_group")
        .get(pk=task_id)
    )
    if task.status != SamplingTask.Status.ASSIGNED:
        raise ValueError("任务当前状态不可执行")
    if task.sampling_batches.filter(status=SamplingBatch.Status.AUTHORIZED).exists():
        raise ValueError("存在待执行的重抽批次，不能重新分配抽样人员")

    current_assignments = list(
        task.personnel_assignments.select_for_update()
        .filter(is_current=True)
        .order_by("id")
    )
    if len(current_assignments) != 1:
        raise ValueError("任务当前分配记录异常")
    previous_assignment = current_assignments[0]
    candidate_user_ids = _require_candidates(task)
    selected_user_id = secrets.choice(candidate_user_ids)

    previous_assignment.is_current = False
    previous_assignment.save(update_fields=["is_current"])
    assignment = PersonnelAssignment.objects.create(
        task=task,
        candidate_user_ids=candidate_user_ids,
        selected_user_id=selected_user_id,
        kind=PersonnelAssignment.Kind.REASSIGN,
        reason=reason,
        is_current=True,
        created_by=actor,
    )
    log_task_event(
        task=task,
        actor=actor,
        event_type="assignment.reassigned",
        before={
            "assignment_id": previous_assignment.id,
            "candidate_user_ids": previous_assignment.candidate_user_ids,
            "selected_user_id": previous_assignment.selected_user_id,
        },
        after={
            "assignment_id": assignment.id,
            "candidate_user_ids": candidate_user_ids,
            "selected_user_id": selected_user_id,
            "reason": reason,
        },
    )
    return assignment
