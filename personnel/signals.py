from django.core.exceptions import ValidationError
from django.db.models.signals import m2m_changed
from django.dispatch import receiver

from accounts.models import User
from personnel.models import PersonnelGroup


@receiver(m2m_changed, sender=PersonnelGroup.members.through)
def validate_personnel_group_members(sender, instance, action, reverse, pk_set, **kwargs):
    if action != "pre_add":
        return

    if reverse:
        invalid_member_exists = instance.role != User.Role.SAMPLER
    else:
        invalid_member_exists = User.objects.filter(pk__in=pk_set).exclude(
            role=User.Role.SAMPLER
        ).exists()
    if invalid_member_exists:
        raise ValidationError("人员分组只能包含抽样人员")
