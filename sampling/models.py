from django.conf import settings
from django.db import models

from personnel.models import PersonnelGroup


class SamplingTask(models.Model):
    class SampleMode(models.TextChoices):
        MATERIAL = "material", "候选物资"
        UNIT = "unit", "样品序号"

    class Status(models.TextChoices):
        DRAFT = "draft", "草稿"
        READY = "ready", "待执行"
        ASSIGNED = "assigned", "待抽样"
        IN_PROGRESS = "in_progress", "进行中"
        COMPLETED = "completed", "已完成"
        CANCELLED = "cancelled", "已取消"

    task_number = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=200)
    sample_mode = models.CharField(max_length=16, choices=SampleMode.choices, default=SampleMode.MATERIAL)
    inspection_type = models.CharField(max_length=100, blank=True)
    purchase_order_number = models.CharField(max_length=100, blank=True)
    order_line_id = models.CharField(max_length=100, blank=True)
    planned_inspection_date = models.DateField(null=True, blank=True)
    receiving_unit = models.CharField(max_length=200, blank=True)
    supplier_name = models.CharField(max_length=200, blank=True)
    material_code = models.CharField(max_length=100, blank=True)
    material_name = models.CharField(max_length=200, blank=True)
    specification = models.CharField(max_length=200, blank=True)
    contact_name = models.CharField(max_length=100, blank=True)
    receiver_phone = models.CharField(max_length=30, blank=True)
    delivery_address = models.CharField(max_length=500, blank=True)
    site_longitude = models.DecimalField(max_digits=12, decimal_places=8, null=True, blank=True)
    site_latitude = models.DecimalField(max_digits=12, decimal_places=8, null=True, blank=True)
    site_geocoded_at = models.DateTimeField(null=True, blank=True)
    site_city = models.CharField(max_length=100, blank=True)
    personnel_group = models.ForeignKey(
        PersonnelGroup, on_delete=models.PROTECT, related_name="sampling_tasks"
    )
    planned_at = models.DateTimeField(null=True, blank=True)
    sample_quantity = models.PositiveIntegerField(null=True, blank=True)
    draw_count = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.DRAFT
    )
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_sampling_tasks",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(draw_count__isnull=True) | models.Q(draw_count__gt=0),
                name="sampling_task_draw_count_positive"
            )
        ]

    def mark_ready(self):
        if self.status != self.Status.DRAFT:
            raise ValueError("只有草稿任务可以设为待执行")
        if self.sample_mode == self.SampleMode.UNIT:
            self.status = self.Status.READY
            self.save(update_fields=["status", "updated_at"])
            return
        candidate_count = self.candidates.count()
        if self.draw_count <= 0:
            raise ValueError("抽取数量必须大于零")
        if self.draw_count > candidate_count:
            raise ValueError("抽取数量不能超过候选物资数量")

        self.status = self.Status.READY
        self.save(update_fields=["status", "updated_at"])

    def __str__(self):
        return self.task_number


class CandidateMaterial(models.Model):
    task = models.ForeignKey(
        SamplingTask, on_delete=models.PROTECT, related_name="candidates"
    )
    material_number = models.CharField(max_length=100)
    order_number = models.CharField(max_length=100)
    supplier = models.CharField(max_length=200)
    material_name = models.CharField(max_length=200)
    quantity = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["task", "material_number"],
                name="unique_material_number_per_task",
            ),
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name="candidate_material_quantity_positive",
            ),
        ]

    def __str__(self):
        return self.material_number


class PersonnelAssignment(models.Model):
    class Kind(models.TextChoices):
        INITIAL = "initial", "首次分配"
        REASSIGN = "reassign", "重新分配"

    task = models.ForeignKey(
        SamplingTask, on_delete=models.PROTECT, related_name="personnel_assignments"
    )
    candidate_user_ids = models.JSONField()
    selected_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="selected_sampling_assignments",
    )
    kind = models.CharField(max_length=16, choices=Kind.choices)
    reason = models.TextField(blank=True)
    is_current = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_sampling_assignments",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    viewed_at = models.DateTimeField(null=True, blank=True)


class SamplingBatch(models.Model):
    class Kind(models.TextChoices):
        INITIAL = "initial", "首次抽样"
        REDRAW = "redraw", "重抽"

    class Status(models.TextChoices):
        AUTHORIZED = "authorized", "已批准"
        LOCKED = "locked", "已锁定"

    task = models.ForeignKey(
        SamplingTask, on_delete=models.PROTECT, related_name="sampling_batches"
    )
    version = models.PositiveIntegerField()
    kind = models.CharField(max_length=16, choices=Kind.choices)
    status = models.CharField(max_length=16, choices=Status.choices)
    reason = models.TextField(blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="approved_sampling_batches",
        null=True,
        blank=True,
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    drawn_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="drawn_sampling_batches",
        null=True,
        blank=True,
    )
    drawn_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["task", "version"], name="unique_sampling_batch_version_per_task"
            )
        ]


class SamplingResult(models.Model):
    batch = models.ForeignKey(
        SamplingBatch, on_delete=models.PROTECT, related_name="results"
    )
    material = models.ForeignKey(
        CandidateMaterial, on_delete=models.PROTECT, related_name="sampling_results",
        null=True, blank=True,
    )
    sample_number = models.PositiveIntegerField(null=True, blank=True)
    sequence = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["batch", "material"], name="unique_material_per_sampling_batch"
            ),
            models.UniqueConstraint(
                fields=["batch", "sequence"], name="unique_sequence_per_sampling_batch"
            ),
            models.UniqueConstraint(
                fields=["batch", "sample_number"], name="unique_sample_number_per_sampling_batch"
            ),
        ]


class SamplingReport(models.Model):
    batch = models.OneToOneField(
        SamplingBatch, on_delete=models.PROTECT, related_name="report"
    )
    inspection_result = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class SamplingPhoto(models.Model):
    batch = models.ForeignKey(SamplingBatch, on_delete=models.CASCADE, related_name="photos")
    path = models.CharField(max_length=500)
    original_name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


class SamplingCheckIn(models.Model):
    class Status(models.TextChoices):
        IN_RANGE = "in_range", "原范围内打卡"
        OUTSIDE = "outside", "原范围外异常打卡"
        SAME_CITY = "same_city", "收货地市内打卡"
        OUTSIDE_CITY = "outside_city", "跨市异常打卡"
        UNAVAILABLE = "unavailable", "定位异常打卡"

    report = models.ForeignKey(
        SamplingReport, on_delete=models.PROTECT, related_name="checkins"
    )
    status = models.CharField(max_length=16, choices=Status.choices)
    latitude = models.DecimalField(max_digits=12, decimal_places=8, null=True, blank=True)
    longitude = models.DecimalField(max_digits=12, decimal_places=8, null=True, blank=True)
    distance_meters = models.PositiveIntegerField(null=True, blank=True)
    location_address = models.CharField(max_length=500, blank=True)
    location_city = models.CharField(max_length=100, blank=True)
    note = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="sampling_checkins", null=True, blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
