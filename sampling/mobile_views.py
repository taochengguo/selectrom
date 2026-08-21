from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import sampler_required
from accounts.forms import ProfileForm
from sampling.models import PersonnelAssignment, SamplingBatch, SamplingTask
from sampling.services.drawing import complete_task, draw_materials


VISIBLE_STATUSES = (
    SamplingTask.Status.ASSIGNED,
    SamplingTask.Status.IN_PROGRESS,
    SamplingTask.Status.COMPLETED,
)


def _owned_tasks(user):
    return SamplingTask.objects.filter(
        personnel_assignments__selected_user=user,
        personnel_assignments__is_current=True,
    ).distinct()


def _owned_task(user, pk):
    return get_object_or_404(
        _owned_tasks(user).select_related("personnel_group"), pk=pk
    )


def _current_assignment(task, user):
    return get_object_or_404(
        PersonnelAssignment,
        task=task,
        selected_user=user,
        is_current=True,
    )


def _latest_locked_batch(task):
    return (
        task.sampling_batches.filter(status=SamplingBatch.Status.LOCKED)
        .prefetch_related("results__material")
        .order_by("-version")
        .first()
    )


def _draw_action(task):
    if task.status != SamplingTask.Status.ASSIGNED:
        return None
    if task.sampling_batches.filter(
        kind=SamplingBatch.Kind.REDRAW,
        status=SamplingBatch.Status.AUTHORIZED,
    ).exists():
        return "redraw"
    if not task.sampling_batches.filter(status=SamplingBatch.Status.LOCKED).exists():
        return "initial"
    return None


def _set_viewed_at_if_current(*, task, assignment, user):
    return PersonnelAssignment.objects.filter(
        pk=assignment.pk,
        task=task,
        selected_user=user,
        is_current=True,
        viewed_at__isnull=True,
    ).update(viewed_at=timezone.now())


def _mark_current_assignment_viewed(task, assignment, user):
    if assignment.viewed_at is not None:
        return task, assignment
    if _set_viewed_at_if_current(task=task, assignment=assignment, user=user):
        assignment.refresh_from_db(fields=["viewed_at"])
        return task, assignment

    task = _owned_task(user, task.pk)
    assignment = _current_assignment(task, user)
    if assignment.viewed_at is None:
        if not _set_viewed_at_if_current(task=task, assignment=assignment, user=user):
            task = _owned_task(user, task.pk)
            assignment = _current_assignment(task, user)
        assignment.refresh_from_db(fields=["viewed_at"])
    return task, assignment


def _serialize_batch(batch):
    persisted_batch = get_object_or_404(
        SamplingBatch.objects.filter(status=SamplingBatch.Status.LOCKED),
        pk=batch.pk,
    )
    persisted_results = persisted_batch.results.select_related("material").order_by(
        "sequence"
    )
    return {
        "batch_id": persisted_batch.pk,
        "batch_status": persisted_batch.status,
        "batch_version": persisted_batch.version,
        "results": [
            {
                "sequence": result.sequence,
                "material_number": result.material.material_number,
                "order_number": result.material.order_number,
                "supplier": result.material.supplier,
                "material_name": result.material.material_name,
                "quantity": result.material.quantity,
                "sampling_quantity": persisted_batch.task.draw_count,
            }
            for result in persisted_results
        ],
    }


@sampler_required
def dashboard(request):
    tasks = _owned_tasks(request.user)
    summary = tasks.aggregate(
        total=Count("id"),
        assigned=Count("id", filter=Q(status=SamplingTask.Status.ASSIGNED)),
        in_progress=Count("id", filter=Q(status=SamplingTask.Status.IN_PROGRESS)),
        completed=Count("id", filter=Q(status=SamplingTask.Status.COMPLETED)),
    )
    recent_tasks = tasks.select_related("personnel_group").order_by(
        "-updated_at", "-id"
    )[:6]
    return render(
        request,
        "mobile/dashboard.html",
        {"summary": summary, "recent_tasks": recent_tasks},
    )


@sampler_required
def reminders(request):
    tasks = _owned_tasks(request.user).select_related("personnel_group")
    # The current assignment is joined explicitly so unread state belongs to this user.
    tasks = tasks.filter(status__in=VISIBLE_STATUSES).order_by("-updated_at", "-id")
    status = request.GET.get("status", "").strip()
    if status in VISIBLE_STATUSES:
        tasks = tasks.filter(status=status)
    assignments = {
        assignment.task_id: assignment
        for assignment in PersonnelAssignment.objects.filter(
            task__in=tasks, selected_user=request.user, is_current=True
        )
    }
    task_rows = [(task, assignments[task.id]) for task in tasks]
    return render(
        request,
        "mobile/reminders.html",
        {
            "task_rows": task_rows,
            "status": status,
            "status_choices": [
                choice for choice in SamplingTask.Status.choices if choice[0] in VISIBLE_STATUSES
            ],
        },
    )


@sampler_required
def task_detail(request, pk):
    task = _owned_task(request.user, pk)
    assignment = _current_assignment(task, request.user)
    task, assignment = _mark_current_assignment_viewed(
        task, assignment, request.user
    )
    batch = _latest_locked_batch(task)
    results = batch.results.select_related("material").order_by("sequence") if batch else ()
    return render(
        request,
        "mobile/task_detail.html",
        {
            "task": task,
            "assignment": assignment,
            "batch": batch,
            "results": results,
            "candidate_count": task.candidates.count(),
            "draw_action": _draw_action(task),
        },
    )


@sampler_required
@require_POST
def task_draw(request, pk):
    task = _owned_task(request.user, pk)
    try:
        batch = draw_materials(task_id=task.pk, actor=request.user)
    except (ValidationError, ValueError) as error:
        return JsonResponse({"error": str(error)}, status=400)
    return JsonResponse(_serialize_batch(batch))


@sampler_required
@require_POST
def task_complete(request, pk):
    task = _owned_task(request.user, pk)
    try:
        complete_task(task_id=task.pk, actor=request.user)
    except (ValidationError, ValueError) as error:
        messages.error(request, str(error))
    else:
        messages.success(request, "任务已完成")
    return redirect("mobile:task-detail", pk=task.pk)


@sampler_required
def profile(request):
    action = request.POST.get("action") if request.method == "POST" else None
    profile_form = ProfileForm(
        request.POST if action != "change_password" else None,
        request.FILES if action != "change_password" else None,
        instance=request.user,
    )
    password_form = PasswordChangeForm(
        request.user,
        request.POST if action == "change_password" else None,
    )
    if request.method == "POST" and action == "change_password":
        if password_form.is_valid():
            user = password_form.save()
            update_session_auth_hash(request, user)
            messages.success(request, "密码已更新")
            return redirect("mobile:profile")
    elif request.method == "POST" and profile_form.is_valid():
        profile_form.save()
        messages.success(request, "个人信息已更新")
        return redirect("mobile:profile")
    return render(
        request,
        "mobile/profile.html",
        {"form": profile_form, "password_form": password_form},
    )
