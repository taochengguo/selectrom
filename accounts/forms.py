from django import forms

from accounts.models import User


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "avatar_choice")
        labels = {"first_name": "昵称", "avatar_choice": "选择头像"}
        widgets = {"avatar_choice": forms.RadioSelect}
