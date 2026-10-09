import csv
import unicodedata

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from audit.services import log_task_event
from sampling.models import CandidateMaterial, SamplingTask
from sampling.services.lifecycle import TaskFrozenError


class CandidateImportError(ValueError):
    pass


REQUIRED_HEADERS = ["物资编号", "订单号", "供应商", "物资名称", "物资数量"]
_FIELD_MAP = {
    "物资编号": "material_number",
    "订单号": "order_number",
    "供应商": "supplier",
    "物资名称": "material_name",
    "物资数量": "quantity",
}
_MUTABLE_TASK_STATUSES = {SamplingTask.Status.DRAFT, SamplingTask.Status.READY}


def _material_number_key(value):
    return unicodedata.normalize("NFC", value).casefold()


def _decode_csv(csv_file):
    content = csv_file.read()
    if isinstance(content, bytes):
        try:
            return content.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise CandidateImportError("CSV 文件必须使用 UTF-8 编码") from error
    return content


def _read_rows(csv_file):
    reader = csv.DictReader(_decode_csv(csv_file).splitlines())
    if reader.fieldnames != REQUIRED_HEADERS:
        expected = "、".join(REQUIRED_HEADERS)
        raise CandidateImportError(f"CSV 表头必须为：{expected}")
    return list(reader)


def _validate_rows(rows, task):
    errors = []
    normalized_rows = []
    seen_numbers = set()
    existing_numbers = {
        _material_number_key(number)
        for number in task.candidates.values_list("material_number", flat=True)
    }

    for row_number, row in enumerate(rows, start=2):
        if None in row:
            errors.append(f"第{row_number}行：列数不正确")
            continue
        values = {field: (row.get(header) or "").strip() for header, field in _FIELD_MAP.items()}
        for header, field in _FIELD_MAP.items():
            if not values[field]:
                errors.append(f"第{row_number}行：{header}不能为空")
        quantity_text = values["quantity"]
        if not quantity_text.isdigit() or int(quantity_text) <= 0:
            errors.append(f"第{row_number}行：物资数量必须是正整数")
            quantity = None
        else:
            quantity = int(quantity_text)

        material_number = values["material_number"]
        if material_number:
            material_number_key = _material_number_key(material_number)
            if material_number_key in seen_numbers:
                errors.append(f"第{row_number}行：物资编号在文件中重复")
            if material_number_key in existing_numbers:
                errors.append(f"第{row_number}行：物资编号已存在于任务中")
            seen_numbers.add(material_number_key)

        if quantity is not None and all(values.values()):
            values["quantity"] = quantity
            candidate = CandidateMaterial(task=task, **values)
            try:
                candidate.full_clean()
            except ValidationError as error:
                messages = []
                for field, field_errors in error.message_dict.items():
                    messages.extend(f"{field}：{message}" for message in field_errors)
                errors.append(f"第{row_number}行：{'；'.join(messages)}")
            else:
                normalized_rows.append((row_number, values))

    if errors:
        raise CandidateImportError("；".join(errors))
    return normalized_rows


def import_candidates(*, task_id, actor, csv_file):
    rows = _read_rows(csv_file)
    with transaction.atomic():
        task = SamplingTask.objects.select_for_update().get(pk=task_id)
        if task.sample_mode == SamplingTask.SampleMode.UNIT:
            raise TaskFrozenError("样品序号抽样任务不使用候选物资")
        if task.status not in _MUTABLE_TASK_STATUSES:
            raise TaskFrozenError("任务已执行，候选物资不可修改")
        validated_rows = _validate_rows(rows, task)
        candidates = [CandidateMaterial(task=task, **row) for _, row in validated_rows]
        try:
            with transaction.atomic():
                CandidateMaterial.objects.bulk_create(candidates)
        except IntegrityError as error:
            duplicate_row = next(
                (
                    row_number
                    for row_number, row in validated_rows
                    if CandidateMaterial.objects.filter(
                        task=task, material_number=row["material_number"]
                    ).exists()
                ),
                validated_rows[0][0] if validated_rows else 2,
            )
            raise CandidateImportError(f"第{duplicate_row}行：物资编号已存在于任务中") from error
        log_task_event(
            task=task,
            actor=actor,
            event_type="materials.imported",
            before={},
            after={
                "count": len(candidates),
                "material_numbers": [candidate.material_number for candidate in candidates],
            },
        )
        return len(candidates)
