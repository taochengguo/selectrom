from django import forms

from accounts.models import User
from personnel.models import PersonnelGroup


class PersonnelGroupForm(forms.ModelForm):
    class Meta:
        model = PersonnelGroup
        fields = ["name", "description", "members"]
        labels = {"name": "分组名称", "description": "分组说明", "members": "抽样人员"}
        help_texts = {"members": "按住 Ctrl 键可选择多位人员。"}
        error_messages = {"name": {"unique": "该分组名称已存在。"}}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["members"].queryset = User.objects.filter(role=User.Role.SAMPLER)
