from django import forms

from sampling.models import CandidateMaterial, SamplingTask


class SamplingTaskForm(forms.ModelForm):
    class Meta:
        model = SamplingTask
        labels = {
            "task_number": "任务编号", "name": "任务名称",
            "personnel_group": "抽样人员分组", "planned_at": "计划时间",
            "draw_count": "抽取数量", "notes": "备注",
        }
        error_messages = {"task_number": {"unique": "该任务编号已存在。"}}
        help_texts = {"planned_at": "格式：2026-09-23 09:00:00"}
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
        labels = {
            "material_number": "物资编号", "order_number": "订单号",
            "supplier": "供应商", "material_name": "物资名称", "quantity": "物资数量",
        }
        fields = [
            "material_number",
            "order_number",
            "supplier",
            "material_name",
            "quantity",
        ]
