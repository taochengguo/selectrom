from django import forms

from accounts.models import User
from personnel.models import PersonnelGroup


class PersonnelGroupForm(forms.ModelForm):
    class Meta:
        model = PersonnelGroup
        fields = ["name", "description", "members"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["members"].queryset = User.objects.filter(role=User.Role.SAMPLER)
