from django import forms

from accounts.models import User
from personnel.models import PersonnelGroup


class SamplerChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, user):
        return user.get_full_name() or "未填写姓名"


class PersonnelGroupForm(forms.ModelForm):
    members = SamplerChoiceField(queryset=User.objects.none(), required=False, label="选择抽样人员", widget=forms.CheckboxSelectMultiple)
    class Meta:
        model = PersonnelGroup
        fields = ["name", "description", "members"]
        labels = {"name": "分组名称", "description": "分组说明", "members": "抽样人员"}
        widgets = {"name": forms.TextInput(attrs={"placeholder": "请输入分组名称"}), "description": forms.Textarea(attrs={"rows": 3, "placeholder": "填写分组用途或说明（选填）"})}
        error_messages = {"name": {"unique": "该分组名称已存在。"}}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["members"].queryset = User.objects.filter(role=User.Role.SAMPLER).order_by("first_name", "username")
