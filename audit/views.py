from datetime import datetime, time

from django.shortcuts import render
from django.core.paginator import Paginator
from django.utils import timezone

from accounts.decorators import admin_required
from audit.models import TaskAuditLog


LOG_CATEGORIES = {
    "account": ("账号与权限", ("user.",)),
    "group": ("人员分组", ("group.",)),
    "task": ("任务与抽样", ("task.", "assignment.", "draw.", "material.", "materials.")),
    "site": ("现场记录", ("checkin.", "report.", "photo.")),
}


def _local_day_boundary(value, *, end=False):
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None
    boundary = datetime.combine(parsed, time.max if end else time.min)
    return timezone.make_aware(boundary, timezone.get_current_timezone())


@admin_required
def log_list(request):
    logs = TaskAuditLog.objects.select_related("task", "actor").all()
    category = request.GET.get("category", "")
    if category in LOG_CATEGORIES:
        from django.db.models import Q
        condition = Q()
        for prefix in LOG_CATEGORIES[category][1]:
            condition |= Q(event_type__startswith=prefix)
        logs = logs.filter(condition)
    else:
        category = ""
    task_number = request.GET.get("task_number", "").strip()
    event_type = request.GET.get("event_type", "").strip()
    actor = request.GET.get("actor", "").strip()
    actor_name = request.GET.get("actor_name", "").strip()
    start_date = request.GET.get("start_date", "").strip()
    end_date = request.GET.get("end_date", "").strip()

    if task_number:
        logs = logs.filter(task__task_number=task_number)
    if event_type:
        logs = logs.filter(event_type=event_type)
    if actor:
        logs = logs.filter(actor__username=actor)
    if actor_name:
        logs = logs.filter(actor__first_name=actor_name)
    start_boundary = _local_day_boundary(start_date) if start_date else None
    if start_boundary is not None:
        logs = logs.filter(created_at__gte=start_boundary)
    end_boundary = _local_day_boundary(end_date, end=True) if end_date else None
    if end_boundary is not None:
        logs = logs.filter(created_at__lte=end_boundary)

    filters = {
        "category": category,
        "task_number": task_number,
        "event_type": event_type,
        "actor": actor,
        "actor_name": actor_name,
        "start_date": start_date,
        "end_date": end_date,
    }
    event_types = TaskAuditLog.objects.order_by("event_type").values_list(
        "event_type", flat=True
    ).distinct()
    page = Paginator(logs, 20).get_page(request.GET.get("page"))
    query = request.GET.copy()
    query.pop("page", None)
    return render(
        request,
        "management/logs/list.html",
        {"logs": page.object_list, "page": page, "filters": filters, "event_types": event_types,
         "categories": [(key, value[0]) for key, value in LOG_CATEGORIES.items()], "query": query.urlencode()},
    )
