from decimal import Decimal
import math

from django.db import transaction
from django.utils import timezone

from sampling.models import SamplingBatch, SamplingCheckIn, SamplingReport, SamplingTask
from sampling.services.tianditu import (
    TiandituServiceError,
    geocode_address,
    reverse_geocode,
)


def _locked_batch(task_id, batch_id):
    return SamplingBatch.objects.select_for_update().get(
        task_id=task_id, pk=batch_id, status=SamplingBatch.Status.LOCKED
    )


@transaction.atomic
def save_inspection_result(*, task_id, batch_id, actor, inspection_result):
    batch = _locked_batch(task_id, batch_id)
    if not batch.task.personnel_assignments.filter(
        selected_user=actor, is_current=True
    ).exists():
        raise ValueError("仅当前抽样人员可以填写报告")
    report, _ = SamplingReport.objects.get_or_create(batch=batch)
    report.inspection_result = inspection_result[:12000]
    report.save(update_fields=["inspection_result", "updated_at"])
    return report


def _site_city(task):
    if not task.delivery_address.strip():
        raise TiandituServiceError("任务没有收货地址，无法确定收货地市")
    if task.site_city:
        return task.site_city
    longitude, latitude = geocode_address(task.delivery_address.strip())
    site_location = reverse_geocode(longitude, latitude)
    task.site_longitude = Decimal(str(longitude))
    task.site_latitude = Decimal(str(latitude))
    task.site_geocoded_at = timezone.now()
    task.site_city = site_location.city
    task.save(update_fields=["site_longitude", "site_latitude", "site_geocoded_at", "site_city", "updated_at"])
    return task.site_city


@transaction.atomic
def record_checkin(*, task_id, batch_id, actor, latitude=None, longitude=None, note=""):
    task = SamplingTask.objects.select_for_update().get(pk=task_id)
    batch = SamplingBatch.objects.select_for_update().get(
        task_id=task_id, pk=batch_id,
        status__in=[SamplingBatch.Status.AUTHORIZED, SamplingBatch.Status.LOCKED],
    )
    if not batch.task.personnel_assignments.filter(
        selected_user=actor, is_current=True
    ).exists():
        raise ValueError("仅当前抽样人员可以现场打卡")
    reported_latitude = reported_longitude = None
    location = None
    site_city = ""
    try:
        if latitude is None or longitude is None:
            raise TiandituServiceError("未能获取设备定位")
        try:
            latitude, longitude = float(latitude), float(longitude)
        except (TypeError, ValueError) as error:
            raise TiandituServiceError("设备定位坐标无效") from error
        if not (
            math.isfinite(latitude)
            and math.isfinite(longitude)
            and -90 <= latitude <= 90
            and -180 <= longitude <= 180
        ):
            raise TiandituServiceError("设备定位坐标无效")
        reported_latitude, reported_longitude = latitude, longitude
        location = reverse_geocode(longitude, latitude)
        site_city = _site_city(task)
        status = (
            SamplingCheckIn.Status.SAME_CITY
            if location.city == site_city else SamplingCheckIn.Status.OUTSIDE_CITY
        )
        unavailable = False
    except TiandituServiceError as error:
        status = SamplingCheckIn.Status.UNAVAILABLE
        unavailable = True
        failure_reason = str(error)
        latitude, longitude = reported_latitude, reported_longitude

    note = (note or "").strip()[:2000]
    abnormal = unavailable or status == SamplingCheckIn.Status.OUTSIDE_CITY
    if abnormal and not note:
        return {
            "requires_note": True,
            "status": status,
            "message": failure_reason if unavailable else (
                f"现场位于{location.city}，收货地址位于{site_city}，请填写跨市打卡备注"
            ),
        }

    report, _ = SamplingReport.objects.get_or_create(batch=batch)
    checkin = SamplingCheckIn.objects.create(
        report=report,
        status=status,
        latitude=Decimal(str(latitude)).quantize(Decimal("0.00000001")) if latitude is not None else None,
        longitude=Decimal(str(longitude)).quantize(Decimal("0.00000001")) if longitude is not None else None,
        distance_meters=None,
        location_address=location.address[:500] if location else "",
        location_city=location.city if location else "",
        note=note,
        created_by=actor,
    )
    return {
        "requires_note": False,
        "checkin_id": checkin.pk,
        "status": checkin.status,
        "status_label": checkin.get_status_display(),
        "actor": actor.get_full_name() or actor.username,
        "location_address": checkin.location_address,
        "location_city": checkin.location_city,
        "note": checkin.note,
        "created_at": checkin.created_at.isoformat(),
    }
