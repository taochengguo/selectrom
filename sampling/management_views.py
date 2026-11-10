from django import forms
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.http import JsonResponse
from django.http import FileResponse
from django.core.files.storage import FileSystemStorage
from django.conf import settings
from django.views.decorators.http import require_GET
from django.contrib.auth.forms import SetPasswordForm, UserCreationForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db.models import Count, Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from accounts.decorators import admin_required
from accounts.models import User
from personnel.models import PersonnelGroup
from sampling.forms import CandidateMaterialForm, SamplingTaskForm, UnitSamplingTaskForm
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
    create_unit_task,
    delete_candidate,
    mark_task_ready,
    update_candidate,
    update_task,
)


class AdminUserCreateForm(forms.ModelForm):
    password1 = forms.CharField(label="密码", strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "new-password", "placeholder": "请输入登录密码"}))

    class Meta:
        model = User
        labels = {"username": "用户名", "first_name": "用户姓名", "role": "用户角色", "is_active": "账号启用"}
        fields = ("username", "password1", "first_name", "role")
        widgets = {"username": forms.TextInput(attrs={"autocomplete": "off", "placeholder": "请输入登录用户名"}), "first_name": forms.TextInput(attrs={"placeholder": "请输入用户姓名"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role"].initial = User.Role.SAMPLER
        self.fields["role"].choices = User.Role.choices
        self.fields["first_name"].required = True

    def _post_clean(self):
        super()._post_clean()
        password = self.cleaned_data.get("password1")
        if password:
            try:
                validate_password(password, self.instance)
            except ValidationError as error:
                self.add_error("password1", error)

    def save(self, commit=True):
        user = super().save(commit=False)
        user.is_active = True
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


class AdminUserProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("username", "first_name")
        labels = {"username": "用户名", "first_name": "用户姓名"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["first_name"].required = True


class AdminUserEditForm(forms.ModelForm):
    class Meta:
        model = User
        labels = {"role": "用户角色", "first_name": "用户姓名", "is_active": "启用账号"}
        fields = (
            "username",
            "role",
            "first_name",
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
def task_list(request, creation_form=None, open_dialog=False):
    tasks = SamplingTask.objects.select_related("personnel_group").order_by(
        "-created_at", "-id"
    )
    status = request.GET.get("status", "").strip()
    if status:
        tasks = tasks.filter(status=status)
    return render(
        request,
        "management/tasks/list.html",
        {
            "tasks": tasks, "status_choices": SamplingTask.Status.choices, "status": status,
            "creation_form": creation_form or UnitSamplingTaskForm(),
            "open_dialog": open_dialog or request.GET.get("create") == "1",
        },
    )


@admin_required
@require_GET
def task_report(request, pk):
    from sampling.services.report_pdf import build_report_pdf, report_filename
    task = get_object_or_404(SamplingTask, pk=pk)
    if task.status != SamplingTask.Status.COMPLETED:
        messages.error(request, "未完成任务，无法查看抽样报告")
        return redirect("management:task-list")
    try:
        filename = report_filename(task)
    except ValueError as error:
        messages.error(request, str(error))
        return redirect("management:task-list")
    batches = task.sampling_batches.filter(status="locked").order_by("-version")
    return FileResponse(build_report_pdf(task, batches, FileSystemStorage(location=settings.SAMPLING_PHOTOS_ROOT)), filename=filename, content_type="application/pdf")


@admin_required
@require_POST
def task_reports_export(request):
    from tempfile import SpooledTemporaryFile
    from zipfile import ZipFile, ZIP_DEFLATED
    from sampling.services.report_pdf import build_report_pdf, report_filename
    field = forms.ModelMultipleChoiceField(queryset=SamplingTask.objects.all())
    try:
        tasks = list(field.clean(request.POST.getlist("tasks")))
    except forms.ValidationError:
        messages.error(request, "请选择有效的任务后再导出")
        return redirect("management:task-list")
    if any(task.status != SamplingTask.Status.COMPLETED for task in tasks):
        messages.error(request, "所选任务中存在未完成任务，无法导出，请仅选择已完成任务")
        return redirect("management:task-list")
    try:
        filenames = [report_filename(task) for task in tasks]
    except ValueError as error:
        messages.error(request, str(error))
        return redirect("management:task-list")
    output = SpooledTemporaryFile(max_size=10 * 1024 * 1024)
    storage = FileSystemStorage(location=settings.SAMPLING_PHOTOS_ROOT)
    try:
        with ZipFile(output, "w", ZIP_DEFLATED) as archive:
            used = set()
            for task, filename in zip(tasks, filenames):
                if filename in used:
                    filename = filename[:-4] + f"_{task.pk}.pdf"
                used.add(filename)
                batches = task.sampling_batches.filter(status="locked").order_by("-version")
                archive.writestr(filename, build_report_pdf(task, batches, storage).getvalue())
        output.seek(0)
        return FileResponse(output, as_attachment=True, filename="抽样报告.zip", content_type="application/zip")
    except Exception:
        output.close()
        raise


@admin_required
def task_create(request):
    if request.method == "GET":
        return redirect(f"{reverse('management:task-list')}?create=1")
    if request.POST.get("mode") == SamplingTask.SampleMode.UNIT:
        form = UnitSamplingTaskForm(request.POST)
        if form.is_valid():
            try:
                task = create_unit_task(actor=request.user, **form.cleaned_data)
            except (ValidationError, ValueError) as error:
                form.add_error(None, _error_text(error))
            else:
                messages.success(request, "抽样任务已创建")
                return redirect("management:task-detail", pk=task.pk)
        return task_list(request, creation_form=form, open_dialog=True)
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
    form_class = UnitSamplingTaskForm if task.sample_mode == SamplingTask.SampleMode.UNIT else SamplingTaskForm
    form = form_class(request.POST or None, instance=task)
    if request.method == "POST" and form.is_valid():
        changes = {
            field: form.cleaned_data[field]
            for field in form.changed_data
            if field in form.cleaned_data
        }
        if task.sample_mode == SamplingTask.SampleMode.UNIT and "material_name" in changes:
            changes["name"] = changes["material_name"] or form.cleaned_data["purchase_order_number"]
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
    assignments = list(task.personnel_assignments.all())
    candidate_ids = {user_id for assignment in assignments for user_id in assignment.candidate_user_ids}
    candidate_users = User.objects.in_bulk(candidate_ids)
    for assignment in assignments:
        assignment.candidate_names = [
            (candidate_users[user_id].get_full_name() or "未填写姓名")
            if user_id in candidate_users else f"人员记录不存在（编号 {user_id}）"
            for user_id in assignment.candidate_user_ids
        ]
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
            "assignments": assignments,
            "reassign_groups": PersonnelGroup.objects.order_by("name") if can_reassign else [],
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
        for field, errors in form.errors.items():
            label = form.fields[field].label if field in form.fields else "物资信息"
            messages.error(request, f"{label}：{'；'.join(errors)}")
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
        personnel_group_id=request.POST.get("personnel_group") or None,
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
    return render(request, "management/users/list.html", {"users": users, "form": AdminUserCreateForm()})


@admin_required
def user_create(request):
    form = AdminUserCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "用户已创建")
        return redirect("management:user-list")
    return render(request, "management/users/list.html", {"form": form, "users": User.objects.order_by("role", "username"), "open_dialog": True})


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
def user_profile(request, pk):
    user = get_object_or_404(User, pk=pk)
    form = AdminUserProfileForm(request.POST, instance=user)
    if not form.is_valid():
        return JsonResponse({"errors": form.errors}, status=400)
    form.save()
    messages.success(request, "用户信息已更新")
    return JsonResponse({"message": "用户信息已更新"})


@admin_required
@require_POST
def user_role(request, pk):
    user = get_object_or_404(User, pk=pk)
    # Reuse edit validation without replacing any other profile fields.
    form = AdminUserEditForm({
        "username": user.username, "first_name": user.first_name,
        "is_active": user.is_active, "role": request.POST.get("role", ""),
    }, instance=user, acting_user=request.user)
    if not form.is_valid():
        return JsonResponse({"errors": form.errors}, status=400)
    form.save()
    return JsonResponse({"message": "用户角色已更新", "role": user.role})


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
        if user.pk == request.user.pk:
            update_session_auth_hash(request, user)
        if request.headers.get("Accept") == "application/json":
            return JsonResponse({"message": "密码已更新"})
        messages.success(request, "密码已重置")
    else:
        if request.headers.get("Accept") == "application/json":
            return JsonResponse({"errors": form.errors}, status=400)
        for field_errors in form.errors.values():
            for error in field_errors:
                messages.error(request, error)
    return redirect("management:user-list")
