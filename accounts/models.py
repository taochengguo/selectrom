from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "管理员"
        SAMPLER = "sampler", "抽样人员"

    role = models.CharField(max_length=16, choices=Role.choices)
    phone = models.CharField(max_length=32, blank=True)
    avatar = models.ImageField(upload_to="avatars/", blank=True)
