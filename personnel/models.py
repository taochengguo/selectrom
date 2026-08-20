from django.db import models

from accounts.models import User


class PersonnelGroup(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    members = models.ManyToManyField(User, blank=True, related_name="personnel_groups")
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="created_personnel_groups"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
