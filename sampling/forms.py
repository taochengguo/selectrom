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


class UnitSamplingTaskForm(forms.ModelForm):
    class Meta:
        model = SamplingTask
        fields = [
            "inspection_type", "purchase_order_number", "order_line_id",
            "planned_inspection_date", "receiving_unit", "supplier_name",
            "material_code", "material_name", "specification", "contact_name",
            "receiver_phone", "delivery_address", "personnel_group",
        ]
        labels = {
            "inspection_type": "质检类型", "purchase_order_number": "抽样采购订单号",
            "order_line_id": "订单行项ID", "planned_inspection_date": "计划抽检日期",
            "receiving_unit": "收货单位", "supplier_name": "供应商名称",
            "material_code": "物资编码", "material_name": "物资名称",
            "specification": "规格型号", "contact_name": "联系人",
            "receiver_phone": "收货人电话", "delivery_address": "收货地址",
            "personnel_group": "抽样人员分组",
        }
        widgets = {"planned_inspection_date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in self.fields:
            self.fields[field_name].required = True


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
