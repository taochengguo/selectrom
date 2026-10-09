from datetime import datetime, time, timedelta
from pathlib import Path
from uuid import uuid4

from PIL import Image, UnidentifiedImageError
from django.conf import settings
from django.core.files.storage import FileSystemStorage

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.http import FileResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from accounts.decorators import sampler_required
from accounts.forms import ProfileForm
from accounts.models import User
from sampling.models import PersonnelAssignment, SamplingBatch, SamplingPhoto, SamplingReport, SamplingTask
from sampling.services.drawing import complete_task, draw_materials
from sampling.services.reports import record_checkin, save_inspection_result


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
    if persisted_batch.task.sample_mode == SamplingTask.SampleMode.UNIT:
        results = [
            {"sequence": result.sequence, "sample_number": result.sample_number}
            for result in persisted_results
        ]
    else:
        results = [
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
        ]
    return {
        "batch_id": persisted_batch.pk,
        "batch_status": persisted_batch.status,
        "batch_version": persisted_batch.version,
        "results": results,
    }


@sampler_required
def dashboard(request):
    tasks = _owned_tasks(request.user)
    today = timezone.localdate()
    today_start = timezone.make_aware(datetime.combine(today, time.min))
    tomorrow_start = today_start + timedelta(days=1)
    summary = tasks.aggregate(
        total=Count("id"),
        today=Count("id", filter=Q(planned_inspection_date=today) | Q(planned_at__gte=today_start, planned_at__lt=tomorrow_start)),
        assigned=Count("id", filter=Q(status=SamplingTask.Status.ASSIGNED)),
        in_progress=Count("id", filter=Q(status=SamplingTask.Status.IN_PROGRESS)),
        completed=Count("id", filter=Q(status=SamplingTask.Status.COMPLETED)),
    )
    query = request.GET.get("q", "").strip()[:100]
    status = request.GET.get("status", "").strip()
    period = request.GET.get("period", "").strip()
    if query:
        tasks = tasks.filter(Q(name__icontains=query) | Q(task_number__icontains=query))
    if status in VISIBLE_STATUSES:
        tasks = tasks.filter(status=status)
    else:
        status = ""
    if period == "today":
        tasks = tasks.filter(Q(planned_inspection_date=today) | Q(planned_at__gte=today_start, planned_at__lt=tomorrow_start))
    else:
        period = ""
    recent_tasks = tasks.select_related("personnel_group").order_by(
        "-updated_at", "-id"
    )[:10]
    return render(
        request,
        "mobile/dashboard.html",
        {"summary": summary, "recent_tasks": recent_tasks, "query": query, "status": status, "period": period},
    )


@sampler_required
def reminders(request):
    tasks = _owned_tasks(request.user).select_related("personnel_group")
    # The current assignment is joined explicitly so unread state belongs to this user.
    tasks = tasks.filter(status__in=VISIBLE_STATUSES).order_by("-updated_at", "-id")
    pending_count = tasks.filter(status=SamplingTask.Status.ASSIGNED).count()
    status = request.GET.get("status", "").strip()
    if status in VISIBLE_STATUSES:
        tasks = tasks.filter(status=status)
    else:
        status = ""
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
            "pending_count": pending_count,
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
    report_batches = list(
        task.sampling_batches.filter(status=SamplingBatch.Status.LOCKED)
        .prefetch_related("results__material", "report__checkins", "photos")
        .order_by("-version")
    )
    for report_batch in report_batches:
        try:
            report_batch.report_record = report_batch.report
        except SamplingReport.DoesNotExist:
            report_batch.report_record = None
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
            "report_batches": report_batches,
        },
    )


@sampler_required
@require_POST
def task_start(request, pk):
    task = _owned_task(request.user, pk)
    if task.status not in (SamplingTask.Status.ASSIGNED, SamplingTask.Status.IN_PROGRESS, SamplingTask.Status.COMPLETED):
        messages.error(request, "当前任务不可开始抽样")
        return redirect("mobile:task-detail", pk=pk)
    with transaction.atomic():
        task = SamplingTask.objects.select_for_update().get(pk=pk)
        if task.status == SamplingTask.Status.ASSIGNED and not task.sampling_batches.exists():
            SamplingBatch.objects.create(
                task=task, version=1, kind=SamplingBatch.Kind.INITIAL,
                status=SamplingBatch.Status.AUTHORIZED,
            )
    return redirect("mobile:task-workflow", pk=pk)


@sampler_required
@require_GET
def task_workflow(request, pk):
    task = _owned_task(request.user, pk)
    batch = task.sampling_batches.order_by("-version").first()
    if batch is None:
        return redirect("mobile:task-detail", pk=pk)
    try:
        report_record = batch.report
    except SamplingReport.DoesNotExist:
        report_record = None
    batch.report_record = report_record
    has_checkin = bool(report_record and report_record.checkins.exists())
    has_photo = batch.photos.exists()
    has_result = bool(report_record and report_record.inspection_result.strip())
    step = (5 if task.status == SamplingTask.Status.COMPLETED else
            1 if not has_checkin else 2 if not has_photo else
            3 if batch.status != SamplingBatch.Status.LOCKED else 4)
    return render(request, "mobile/task_workflow.html", {
        "task": task, "batch": batch, "report_batch": batch,
        "results": batch.results.select_related("material").order_by("sequence"),
        "draw_action": _draw_action(task), "step": step,
        "has_checkin": has_checkin, "has_photo": has_photo,
        "has_result": has_result,
    })


@sampler_required
@require_POST
def task_draw(request, pk):
    task = _owned_task(request.user, pk)
    prepared = task.sampling_batches.filter(
        kind=SamplingBatch.Kind.INITIAL, status=SamplingBatch.Status.AUTHORIZED
    ).first()
    if prepared and (not prepared.photos.exists() or not SamplingReport.objects.filter(
        batch=prepared, checkins__isnull=False
    ).exists()):
        return JsonResponse({"error": "请先完成现场打卡并上传编号样品照片"}, status=400)
    try:
        batch = draw_materials(
            task_id=task.pk, actor=request.user,
            sample_quantity=request.POST.get("sample_quantity"),
            draw_count=request.POST.get("draw_count"),
        )
    except (ValidationError, ValueError) as error:
        return JsonResponse({"error": str(error)}, status=400)
    return JsonResponse(_serialize_batch(batch))


@sampler_required
@require_POST
def task_report_save(request, pk, batch_id):
    task = _owned_task(request.user, pk)
    try:
        report = save_inspection_result(
            task_id=task.pk,
            batch_id=batch_id,
            actor=request.user,
            inspection_result=request.POST.get("inspection_result", ""),
        )
    except (SamplingBatch.DoesNotExist, ValueError) as error:
        return JsonResponse({"error": str(error) or "抽样记录不存在"}, status=400)
    return JsonResponse({"saved": True, "updated_at": report.updated_at.isoformat()})


def _photo_batch(request, pk, batch_id):
    task = _owned_task(request.user, pk)
    return get_object_or_404(task.sampling_batches, pk=batch_id, status__in=[SamplingBatch.Status.AUTHORIZED, SamplingBatch.Status.LOCKED])


def _photo_storage():
    return FileSystemStorage(location=settings.SAMPLING_PHOTOS_ROOT)


@sampler_required
@require_POST
def task_report_photos(request, pk, batch_id):
    batch = _photo_batch(request, pk, batch_id)
    upload = request.FILES.get("photo")
    if upload is None:
        return JsonResponse({"error": "请选择照片"}, status=400)
    if upload.size > 10 * 1024 * 1024:
        return JsonResponse({"error": "单张照片不能超过 10 MB"}, status=400)
    try:
        with Image.open(upload) as image:
            image.verify()
            image_format = image.format
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
        return JsonResponse({"error": "请选择有效的图片文件"}, status=400)
    if image_format not in {"JPEG", "PNG", "WEBP"}:
        return JsonResponse({"error": "仅支持 JPG、PNG 或 WebP 图片"}, status=400)
    upload.seek(0)
    from django.db import transaction
    with transaction.atomic():
        SamplingBatch.objects.select_for_update().get(pk=batch.pk)
        if batch.photos.count() >= 3:
            return JsonResponse({"error": "最多上传 3 张照片"}, status=400)
        extension = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}[image_format]
        path = _photo_storage().save(f"{batch.task_id}/{batch.pk}/{uuid4().hex}{extension}", upload)
        photo = SamplingPhoto.objects.create(batch=batch, path=path, original_name=Path(upload.name).name[:255])
    return JsonResponse({"photo": _photo_data(photo)}, status=201)


def _photo_data(photo):
    from django.urls import reverse
    return {
        "id": photo.pk, "path": photo.path, "name": photo.original_name,
        "url": reverse("mobile:task-report-photo", args=[photo.batch.task_id, photo.batch_id, photo.pk]),
        "delete_url": reverse("mobile:task-report-photo-delete", args=[photo.batch.task_id, photo.batch_id, photo.pk]),
    }


@sampler_required
@require_GET
def task_report_photo(request, pk, batch_id, photo_id):
    batch = _photo_batch(request, pk, batch_id)
    photo = get_object_or_404(batch.photos, pk=photo_id)
    storage = _photo_storage()
    if not storage.exists(photo.path):
        from django.http import Http404
        raise Http404("照片不存在")
    return FileResponse(storage.open(photo.path, "rb"), content_type={".jpg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}.get(Path(photo.path).suffix))


@sampler_required
@require_POST
def task_report_photo_delete(request, pk, batch_id, photo_id):
    batch = _photo_batch(request, pk, batch_id)
    photo = get_object_or_404(batch.photos, pk=photo_id)
    path = photo.path
    photo.delete()
    _photo_storage().delete(path)
    return JsonResponse({"deleted": True})


@sampler_required
@require_POST
def task_report_checkin(request, pk, batch_id):
    task = _owned_task(request.user, pk)
    try:
        result = record_checkin(
            task_id=task.pk,
            batch_id=batch_id,
            actor=request.user,
            latitude=request.POST.get("latitude") or None,
            longitude=request.POST.get("longitude") or None,
            note=request.POST.get("note", ""),
        )
    except (SamplingBatch.DoesNotExist, ValueError) as error:
        return JsonResponse({"error": str(error) or "无法完成现场打卡"}, status=400)
    return JsonResponse(result)


@sampler_required
@require_POST
def task_complete(request, pk):
    task = _owned_task(request.user, pk)
    batch = _latest_locked_batch(task)
    report = SamplingReport.objects.filter(batch=batch).first() if batch else None
    if batch and batch.photos.exists() and report and report.checkins.exists() and not report.inspection_result.strip():
        messages.error(request, "请先填写并保存抽样检测结论")
        return redirect("mobile:task-workflow", pk=pk)
    try:
        complete_task(task_id=task.pk, actor=request.user)
    except (ValidationError, ValueError) as error:
        messages.error(request, str(error))
    else:
        messages.success(request, "任务已完成")
    if batch and batch.photos.exists():
        return redirect("mobile:task-workflow", pk=task.pk)
    return redirect("mobile:task-detail", pk=task.pk)


@sampler_required
def profile(request):
    action = request.POST.get("action") if request.method == "POST" else None
    profile_form = ProfileForm(
        request.POST if action == "update_profile" else None,
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
    elif request.method == "POST" and action == "update_profile" and profile_form.is_valid():
        profile_form.save()
        messages.success(request, "个人信息已更新")
        return redirect("mobile:profile")
    summary = _owned_tasks(request.user).aggregate(
        total=Count("id"),
        assigned=Count("id", filter=Q(status=SamplingTask.Status.ASSIGNED)),
        completed=Count("id", filter=Q(status=SamplingTask.Status.COMPLETED)),
    )
    return render(
        request,
        "mobile/profile.html",
        {
            "form": profile_form,
            "password_form": password_form,
            "summary": summary,
            "avatar_url": static(f"img/{request.user.avatar_choice}.png"),
            "avatar_options": [
                {"value": value, "label": label, "url": static(f"img/{value}.png")}
                for value, label in User.AvatarChoice.choices
            ],
        },
    )
