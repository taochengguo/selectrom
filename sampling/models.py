from django.conf import settings
from django.db import models

from personnel.models import PersonnelGroup


class SamplingTask(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "草稿"
        READY = "ready", "待执行"
        ASSIGNED = "assigned", "待抽样"
        IN_PROGRESS = "in_progress", "进行中"
        COMPLETED = "completed", "已完成"
        CANCELLED = "cancelled", "已取消"

    task_number = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=200)
    personnel_group = models.ForeignKey(
        PersonnelGroup, on_delete=models.PROTECT, related_name="sampling_tasks"
    )
    planned_at = models.DateTimeField(null=True, blank=True)
    draw_count = models.PositiveIntegerField()
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
                condition=models.Q(draw_count__gt=0), name="sampling_task_draw_count_positive"
            )
        ]

    def mark_ready(self):
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
        CandidateMaterial, on_delete=models.PROTECT, related_name="sampling_results"
    )
    sequence = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["batch", "material"], name="unique_material_per_sampling_batch"
            ),
            models.UniqueConstraint(
                fields=["batch", "sequence"], name="unique_sequence_per_sampling_batch"
            ),
        ]
