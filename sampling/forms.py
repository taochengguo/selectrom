from django import forms

from sampling.models import CandidateMaterial, SamplingTask


class SamplingTaskForm(forms.ModelForm):
    class Meta:
        model = SamplingTask
        fields = [
            "task_number",
            "name",
            "personnel_group",
            "planned_at",
            "draw_count",
            "notes",
        ]


class CandidateMaterialForm(forms.ModelForm):
    class Meta:
        model = CandidateMaterial
        fields = [
            "material_number",
            "order_number",
            "supplier",
            "material_name",
            "quantity",
        ]
