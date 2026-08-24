from django import forms
from django.contrib import messages
from django.contrib.auth.forms import SetPasswordForm, UserCreationForm
from django.core.exceptions import ValidationError
from django.db.models import Count, Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.decorators import admin_required
from accounts.models import User
from sampling.forms import CandidateMaterialForm, SamplingTaskForm
from sampling.models import (
    CandidateMaterial,
    SamplingBatch,
    SamplingResult,
    SamplingTask,
)
from sampling.services.assignment import assign_sampler, reassign_sampler
from sampling.services.drawing import authorize_redraw
from sampling.services.imports import CandidateImportError, import_candidates
from sampling.services.lifecycle import (
    TaskFrozenError,
    cancel_task,
    create_candidate,
    create_task,
    delete_candidate,
    mark_task_ready,
    update_candidate,
    update_task,
)


class AdminUserCreateForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = (
            "username",
            "role",
            "first_name",
            "last_name",
            "phone",
            "is_active",
        )


class AdminUserEditForm(forms.ModelForm):
    class Meta:
        model = User
        fields = (
            "username",
            "role",
            "first_name",
            "last_name",
            "phone",
            "is_active",
        )

    def __init__(self, *args, acting_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.acting_user = acting_user

    def clean_role(self):
        role = self.cleaned_data["role"]
        if (
            self.acting_user is not None
            and self.instance.pk == self.acting_user.pk
            and role != User.Role.ADMIN
        ):
            raise forms.ValidationError("当前登录账号必须保留管理员角色")
        if (
            role == User.Role.ADMIN
            and self.instance.pk
            and self.instance.personnel_groups.exists()
        ):
            raise forms.ValidationError("请先将该用户移出所有抽样人员分组")
        return role

    def clean_is_active(self):
        is_active = self.cleaned_data["is_active"]
        if (
            self.acting_user is not None
            and self.instance.pk == self.acting_user.pk
            and not is_active
        ):
            raise forms.ValidationError("不能停用当前登录账号")
        return is_active


def _error_text(error):
    if isinstance(error, ValidationError):
        if hasattr(error, "message_dict"):
            return "；".join(
                f"{field}：{'、'.join(field_messages)}"
                for field, field_messages in error.message_dict.items()
            )
        return "；".join(error.messages)
    return str(error)


def _service_error(request, error):
    messages.error(request, _error_text(error))


@admin_required
def dashboard(request):
    counts = {
        row["status"]: row["total"]
        for row in SamplingTask.objects.values("status").annotate(total=Count("id"))
    }
    summary = {
        "total": sum(counts.values()),
        "ready": counts.get(SamplingTask.Status.READY, 0),
        "assigned": counts.get(SamplingTask.Status.ASSIGNED, 0),
        "in_progress": counts.get(SamplingTask.Status.IN_PROGRESS, 0),
        "completed": counts.get(SamplingTask.Status.COMPLETED, 0),
    }
    recent_tasks = SamplingTask.objects.select_related("personnel_group").order_by(
        "-created_at", "-id"
    )[:8]
    return render(
        request,
        "management/dashboard.html",
        {"summary": summary, "recent_tasks": recent_tasks},
    )


@admin_required
def task_list(request):
    tasks = SamplingTask.objects.select_related("personnel_group").order_by(
        "-created_at", "-id"
    )
    status = request.GET.get("status", "").strip()
    if status:
        tasks = tasks.filter(status=status)
    return render(
        request,
        "management/tasks/list.html",
        {"tasks": tasks, "status_choices": SamplingTask.Status.choices, "status": status},
    )


@admin_required
def task_create(request):
    form = SamplingTaskForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            task = create_task(actor=request.user, **form.cleaned_data)
        except (ValidationError, ValueError) as error:
            form.add_error(None, _error_text(error))
        else:
            messages.success(request, "抽样任务已创建")
            return redirect("management:task-detail", pk=task.pk)
    return render(request, "management/tasks/form.html", {"form": form})


@admin_required
def task_edit(request, pk):
    task = get_object_or_404(SamplingTask, pk=pk)
    form = SamplingTaskForm(request.POST or None, instance=task)
    if request.method == "POST" and form.is_valid():
        changes = {
            field: form.cleaned_data[field]
            for field in form.changed_data
            if field in form.cleaned_data
        }
        try:
            if changes:
                update_task(task_id=task.pk, actor=request.user, **changes)
        except (ValidationError, ValueError) as error:
            form.add_error(None, _error_text(error))
        else:
            messages.success(request, "抽样任务已更新")
            return redirect("management:task-detail", pk=task.pk)
    return render(request, "management/tasks/form.html", {"form": form, "task": task})


@admin_required
def task_detail(request, pk):
    task = get_object_or_404(
        SamplingTask.objects.select_related("personnel_group", "created_by").prefetch_related(
            "candidates",
            "personnel_assignments__selected_user",
            "personnel_assignments__created_by",
            Prefetch(
                "sampling_batches",
                queryset=SamplingBatch.objects.order_by("version").prefetch_related(
                    Prefetch(
                        "results",
                        queryset=SamplingResult.objects.select_related("material").order_by(
                            "sequence"
                        ),
                    )
                ),
            ),
            "audit_logs__actor",
        ),
        pk=pk,
    )
    has_pending_redraw = any(
        batch.status == SamplingBatch.Status.AUTHORIZED
        for batch in task.sampling_batches.all()
    )
    can_reassign = (
        task.status == SamplingTask.Status.ASSIGNED and not has_pending_redraw
    )
    return render(
        request,
        "management/tasks/detail.html",
        {
            "task": task,
            "candidate_form": CandidateMaterialForm(),
            "has_pending_redraw": has_pending_redraw,
            "can_reassign": can_reassign,
        },
    )


@admin_required
def task_import(request, pk):
    task = get_object_or_404(SamplingTask, pk=pk)
    if request.method == "POST":
        csv_file = request.FILES.get("csv_file")
        if csv_file is None:
            messages.error(request, "请选择 CSV 文件")
        else:
            try:
                count = import_candidates(
                    task_id=task.pk, actor=request.user, csv_file=csv_file
                )
            except (CandidateImportError, TaskFrozenError, ValidationError, ValueError) as error:
                _service_error(request, error)
            else:
                messages.success(request, f"已导入 {count} 条候选物资")
                return redirect("management:task-detail", pk=task.pk)
    return render(request, "management/tasks/import.html", {"task": task})


@admin_required
@require_POST
def task_candidate_add(request, pk):
    task = get_object_or_404(SamplingTask, pk=pk)
    form = CandidateMaterialForm(request.POST)
    if form.is_valid():
        try:
            create_candidate(task_id=task.pk, actor=request.user, **form.cleaned_data)
        except (ValidationError, ValueError) as error:
            _service_error(request, error)
        else:
            messages.success(request, "候选物资已添加")
    else:
        messages.error(request, _error_text(ValidationError(form.errors.as_json())))
    return redirect("management:task-detail", pk=task.pk)


@admin_required
def task_candidate_edit(request, pk):
    candidate = get_object_or_404(CandidateMaterial, pk=pk)
    form = CandidateMaterialForm(request.POST or None, instance=candidate)
    if request.method == "POST" and form.is_valid():
        changes = {
            field: form.cleaned_data[field]
            for field in form.changed_data
            if field in form.cleaned_data
        }
        try:
            if changes:
                update_candidate(
                    candidate_id=candidate.pk, actor=request.user, **changes
                )
        except (ValidationError, ValueError) as error:
            form.add_error(None, _error_text(error))
        else:
            messages.success(request, "候选物资已更新")
            return redirect("management:task-detail", pk=candidate.task_id)
    return render(
        request,
        "management/tasks/candidate_form.html",
        {"form": form, "candidate": candidate, "task": candidate.task},
    )


@admin_required
@require_POST
def task_candidate_delete(request, pk):
    candidate = get_object_or_404(CandidateMaterial, pk=pk)
    task_id = candidate.task_id
    try:
        delete_candidate(candidate_id=candidate.pk, actor=request.user)
    except (ValidationError, ValueError) as error:
        _service_error(request, error)
    else:
        messages.success(request, "候选物资已删除")
    return redirect("management:task-detail", pk=task_id)


def _task_action(request, pk, service, success_message, **kwargs):
    task = get_object_or_404(SamplingTask, pk=pk)
    try:
        service(task_id=task.pk, actor=request.user, **kwargs)
    except (ValidationError, ValueError) as error:
        _service_error(request, error)
    else:
        messages.success(request, success_message)
    return redirect("management:task-detail", pk=task.pk)


@admin_required
@require_POST
def task_ready(request, pk):
    return _task_action(request, pk, mark_task_ready, "任务已进入待执行状态")


@admin_required
@require_POST
def task_execute(request, pk):
    return _task_action(request, pk, assign_sampler, "已随机分配抽样人员")


@admin_required
@require_POST
def task_reassign(request, pk):
    return _task_action(
        request,
        pk,
        reassign_sampler,
        "已重新随机分配抽样人员",
        reason=request.POST.get("reason", ""),
    )


@admin_required
@require_POST
def task_authorize_redraw(request, pk):
    return _task_action(
        request,
        pk,
        authorize_redraw,
        "重抽已批准",
        reason=request.POST.get("reason", ""),
    )


@admin_required
@require_POST
def task_cancel(request, pk):
    return _task_action(request, pk, cancel_task, "任务已取消")


@admin_required
def user_list(request):
    users = User.objects.order_by("role", "username")
    return render(request, "management/users/list.html", {"users": users})


@admin_required
def user_create(request):
    form = AdminUserCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "用户已创建")
        return redirect("management:user-list")
    return render(request, "management/users/form.html", {"form": form})


@admin_required
def user_edit(request, pk):
    user = get_object_or_404(User, pk=pk)
    form = AdminUserEditForm(
        request.POST or None, instance=user, acting_user=request.user
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "用户信息已更新")
        return redirect("management:user-list")
    return render(request, "management/users/form.html", {"form": form, "managed_user": user})


@admin_required
@require_POST
def user_toggle_active(request, pk):
    user = get_object_or_404(User, pk=pk)
    if user.pk == request.user.pk and user.is_active:
        messages.error(request, "不能停用当前登录账号")
    else:
        user.is_active = not user.is_active
        user.save(update_fields=["is_active"])
        messages.success(request, "用户状态已更新")
    return redirect("management:user-list")


@admin_required
@require_POST
def user_reset_password(request, pk):
    user = get_object_or_404(User, pk=pk)
    password_data = request.POST.copy()
    password_data.setdefault("new_password1", request.POST.get("password1", ""))
    password_data.setdefault("new_password2", request.POST.get("password2", ""))
    form = SetPasswordForm(user, password_data)
    if form.is_valid():
        form.save()
        messages.success(request, "密码已重置")
    else:
        for field_errors in form.errors.values():
            for error in field_errors:
                messages.error(request, error)
    return redirect("management:user-list")
