from django.conf import settings
from django.db import models

from sampling.models import SamplingTask


class TaskAuditLog(models.Model):
    task = models.ForeignKey(
        SamplingTask, on_delete=models.PROTECT, related_name="audit_logs"
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="task_audit_logs",
    )
    event_type = models.CharField(max_length=100)
    before_data = models.JSONField(default=dict)
    after_data = models.JSONField(default=dict)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
