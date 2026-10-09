from django import template

from sampling.models import SamplingTask


register = template.Library()

EVENT_LABELS = {
    "task.created": "创建任务", "task.updated": "更新任务",
    "task.ready": "设为待执行", "task.cancelled": "取消任务",
    "task.completed": "完成任务", "material.created": "添加候选物资",
    "material.updated": "更新候选物资", "material.deleted": "删除候选物资",
    "materials.imported": "导入候选物资", "assignment.initial": "首次分配人员",
    "assignment.reassigned": "重新分配人员", "draw.initial": "首次抽样",
    "draw.redraw": "重新抽样", "draw.redraw_authorized": "批准重抽",
    "task.sample_counts_set": "填写样品数量",
}

FIELD_LABELS = {
    "id": "编号", "task_number": "任务编号", "name": "任务名称",
    "personnel_group_id": "抽样组编号", "planned_at": "计划时间",
    "draw_count": "抽取数量", "status": "状态", "notes": "备注",
    "material_number": "物资编号", "order_number": "订单号",
    "supplier": "供应商", "material_name": "物资名称", "quantity": "物资数量",
    "batch_id": "批次编号", "version": "版本", "material_ids": "物资记录编号",
    "assignment_id": "分配记录编号", "candidate_user_ids": "候选人员编号",
    "selected_user_id": "选中人员编号", "reason": "原因", "count": "数量",
    "material_numbers": "物资编号列表",
    "sample_mode": "抽样方式", "sample_quantity": "样品数量",
    "inspection_type": "质检类型", "purchase_order_number": "抽样采购订单号",
    "order_line_id": "订单行项ID", "planned_inspection_date": "计划抽检日期",
    "receiving_unit": "收货单位", "supplier_name": "供应商名称",
    "material_code": "物资编码", "specification": "规格型号",
    "contact_name": "联系人", "receiver_phone": "收货人电话",
    "delivery_address": "收货地址", "sample_numbers": "抽样样品序号",
}


@register.filter
def event_label(value):
    return EVENT_LABELS.get(value, value)


@register.filter
def audit_data(value):
    if not isinstance(value, dict):
        return value
    entries = []
    for key, item in value.items():
        if key == "status":
            item = dict(SamplingTask.Status.choices).get(item, item)
        if item is None or item == "":
            item = "未设置"
        elif isinstance(item, list):
            item = "、".join(str(entry) for entry in item) or "无"
        entries.append(f"{FIELD_LABELS.get(key, key)}：{item}")
    return "；".join(entries) or "无"
