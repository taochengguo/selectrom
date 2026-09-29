from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "管理员"
        SAMPLER = "sampler", "抽样人员"

    class AvatarChoice(models.TextChoices):
        ICON1 = "icon1", "头像 1"
        ICON2 = "icon2", "头像 2"
        ICON3 = "icon3", "头像 3"
        ICON4 = "icon4", "头像 4"
        ICON5 = "icon5", "头像 5"

    role = models.CharField(max_length=16, choices=Role.choices)
    phone = models.CharField(max_length=32, blank=True)
    avatar = models.ImageField(upload_to="avatars/", blank=True)
    avatar_choice = models.CharField(
        max_length=5, choices=AvatarChoice.choices, default=AvatarChoice.ICON1
    )
