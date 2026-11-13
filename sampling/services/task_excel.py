"""Read weekly plans and create tasks only after a validated, editable preview."""
from datetime import date, datetime
from io import BytesIO
import json
from zipfile import ZipFile

from django import forms
from django.db import transaction
from openpyxl import load_workbook

from personnel.models import PersonnelGroup
from sampling.forms import UnitSamplingTaskForm
from sampling.models import SamplingTask
from sampling.services.lifecycle import create_unit_task


MAX_ROWS = 500
MAX_BYTES = 5 * 1024 * 1024
SOURCE_FIELDS = ('source_sequence', 'source_sampler', 'source_completed_count', 'source_status')
HEADERS = {
    '序号': 'source_sequence', '质检类型': 'inspection_type',
    '抽样采购订单号': 'purchase_order_number', '订单行项ID': 'order_line_id',
    '计划抽检日期': 'planned_inspection_date', '收货单位': 'receiving_unit',
    '供应商名称': 'supplier_name', '物资编码': 'material_code',
    '物资名称': 'material_name', '规格型号': 'specification',
    '抽样样品数': 'draw_count', '抽样人员': 'source_sampler',
    '完成样品数': 'source_completed_count', '检查状态': 'source_status',
    '联系人': 'contact_name', '收货人电话': 'receiver_phone',
    '收货地址': 'delivery_address', '备注': 'notes',
    '详细地址': 'detailed_address', '品类名称': 'category_name',
    '样品数量': 'sample_quantity',
}


class ExcelTaskForm(UnitSamplingTaskForm):
    source_sequence = forms.CharField(label='原表序号', required=False, max_length=100, strip=False)
    source_sampler = forms.CharField(label='原表抽样人员', required=False, max_length=200, strip=False)
    source_completed_count = forms.CharField(label='原表完成样品数', required=False, max_length=100, strip=False)
    source_status = forms.CharField(label='原表检查状态', required=False, max_length=100, strip=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields.pop('personnel_group')
        for field in self.fields.values():
            if isinstance(field, forms.CharField):
                field.strip = False
        self.fields['notes'].widget = forms.Textarea(attrs={'rows': 2})

    def clean_purchase_order_number(self):
        value = self.cleaned_data['purchase_order_number']
        if not value.strip():
            raise forms.ValidationError('请填写抽样采购订单号。')
        return value


def _cell_text(cell):
    value = cell.value
    if value is None:
        return ''
    if cell.data_type in ('f', 'e'):
        raise ValueError(f'单元格 {cell.coordinate} 包含公式或错误值，请先转换为实际值。')
    if isinstance(value, (date, datetime)):
        return value.strftime('%Y-%m-%d')
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    # Preserve identifiers formatted with leading zeros in Excel.
    if isinstance(value, int) and cell.number_format and set(cell.number_format) == {'0'}:
        return str(value).zfill(len(cell.number_format))
    return str(value)


def parse_task_workbook(upload):
    if not upload.name.lower().endswith('.xlsx'):
        raise ValueError('请选择 .xlsx 格式的 Excel 文件。')
    if upload.size > MAX_BYTES:
        raise ValueError('文件不能超过 5MB。')
    workbook = None
    try:
        contents = upload.read(MAX_BYTES + 1)
        if len(contents) > MAX_BYTES:
            raise ValueError('文件不能超过 5MB。')
        with ZipFile(BytesIO(contents)) as archive:
            if sum(info.file_size for info in archive.infolist()) > 40 * 1024 * 1024:
                raise ValueError('文件解压后过大，请拆分后导入。')
        workbook = load_workbook(BytesIO(contents), read_only=True, data_only=False, keep_links=False)
        if len(workbook.worksheets) != 1:
            raise ValueError('请保留一个包含任务数据的工作表后导入。')
        sheet = workbook.worksheets[0]
        sheet.reset_dimensions()
        iterator = sheet.iter_rows()
        header_cells = next(iterator, ())
        if len(header_cells) > 30:
            raise ValueError('表格列数过多，最多支持30列。')
        headers = [_cell_text(cell).strip() for cell in header_cells]
        nonempty = [h for h in headers if h]
        if '抽样采购订单号' not in nonempty:
            raise ValueError('表头缺少“抽样采购订单号”。')
        if len(set(nonempty)) != len(nonempty):
            raise ValueError('表头存在重复列，请修改后上传。')
        unknown = set(nonempty) - HEADERS.keys()
        if unknown:
            raise ValueError('无法识别的列：' + '、'.join(sorted(unknown)))
        rows = []
        for index, cells in enumerate(iterator, 2):
            if index > 5002:
                raise ValueError('表格行数过多，请删除多余空白行后上传。')
            if len(cells) > 30:
                raise ValueError(f'第{index}行列数过多。')
            values = [_cell_text(cell) for cell in cells]
            if not any(value != '' for value in values):
                continue
            data = {}
            for col, value in enumerate(values):
                header = headers[col] if col < len(headers) else ''
                if not header and value:
                    raise ValueError(f'第{index}行存在无表头数据，请补全表头。')
                if header:
                    data[HEADERS[header]] = value
            rows.append({'row_number': index, 'data': data})
            if len(rows) > MAX_ROWS:
                raise ValueError('每次最多导入500条任务，请拆分文件。')
        if not rows:
            raise ValueError('表格没有可导入的任务数据。')
        return rows
    except ValueError:
        raise
    except Exception as error:
        raise ValueError('无法读取 Excel 文件，请确认文件未损坏且为有效的 .xlsx 文件。') from error
    finally:
        if workbook is not None:
            workbook.close()


def _form_values(form, group):
    values = {key: value for key, value in form.cleaned_data.items() if key not in SOURCE_FIELDS}
    values['personnel_group'] = group
    values['source_metadata'] = {key: form.cleaned_data[key] for key in SOURCE_FIELDS}
    return values


def _signature(values):
    # Compare all current imported business data, not status/IDs generated by this system.
    result = dict(values)
    result['personnel_group'] = result['personnel_group'].pk
    result['source_metadata'] = {key: result.get('source_metadata', {}).get(key, '') for key in SOURCE_FIELDS}
    return json.dumps(result, sort_keys=True, ensure_ascii=False, default=str)


def _existing_signatures(rows, group):
    orders = {row['form'].cleaned_data.get('purchase_order_number') for row in rows if row['form'].is_valid()}
    fields = list(ExcelTaskForm._meta.fields)
    fields.remove('personnel_group')
    signatures = set()
    for task in SamplingTask.objects.filter(sample_mode='unit', personnel_group=group, purchase_order_number__in=orders):
        values = {field: getattr(task, field) for field in fields}
        values.update(personnel_group=group, source_metadata=task.source_metadata)
        signatures.add(_signature(values))
    return signatures


def prepare_rows(rows, group):
    prepared = []
    for index, row in enumerate(rows):
        prefix = f'row-{index}'
        form = ExcelTaskForm({f'{prefix}-{key}': value for key, value in row['data'].items()}, prefix=prefix)
        form.is_valid()
        prepared.append({**row, 'form': form, 'duplicate': False})
    seen = _existing_signatures(prepared, group) if group else set()
    for row in prepared:
        if row['form'].is_valid() and group:
            key = _signature(_form_values(row['form'], group))
            row['duplicate'] = key in seen
            seen.add(key)
    return prepared


@transaction.atomic
def commit_rows(rows, group, actor):
    # All imports choosing the same group serialize their final duplicate check.
    group = PersonnelGroup.objects.select_for_update().get(pk=group.pk)
    prepared = prepare_rows(rows, group)
    if not prepared:
        raise ValueError('请至少保留一条任务。')
    if any(not row['form'].is_valid() for row in prepared):
        raise ValueError('存在未通过校验的任务，请修改或删除后再确认导入。')
    created, skipped = [], 0
    for row in prepared:
        if row['duplicate']:
            skipped += 1
        else:
            created.append(create_unit_task(actor=actor, **_form_values(row['form'], group)))
    return created, skipped
