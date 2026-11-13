from datetime import date
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from openpyxl import Workbook

from accounts.models import User
from personnel.models import PersonnelGroup
from sampling.models import SamplingTask


HEADERS = ['序号', '质检类型', '抽样采购订单号', '订单行项ID', '计划抽检日期', '收货单位', '供应商名称', '物资编码', '物资名称', '规格型号', '抽样样品数', '抽样人员', '完成样品数', '检查状态', '联系人', '收货人电话', '收货地址', '备注', '详细地址', '品类名称']
VALUES = [1, '省采检测', 'PO-100', '184633613690699', date(2026, 8, 17), '收货单位', '供应商', '00123', '拉盘', '-', 1, '', '', '待抽样', '联系人', '013955758120', '宿州', '备注', '宿州XX区', '水泥拉盘']


def upload(headers=None, rows=None):
    wb = Workbook()
    wb.active.append(HEADERS if headers is None else headers)
    for row in [VALUES] if rows is None else rows:
        wb.active.append(row)
    output = BytesIO()
    wb.save(output)
    return SimpleUploadedFile('计划.xlsx', output.getvalue())


class TaskExcelTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user('excel-admin', role=User.Role.ADMIN)
        self.group = PersonnelGroup.objects.create(name='导入组', created_by=self.admin)

    def test_parser_preserves_identifiers_and_maps_quantity_and_source(self):
        from sampling.services.task_excel import parse_task_workbook
        rows = parse_task_workbook(upload())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['data']['draw_count'], '1')
        self.assertEqual(rows[0]['data']['receiver_phone'], '013955758120')
        self.assertEqual(rows[0]['data']['order_line_id'], '184633613690699')
        self.assertEqual(rows[0]['data']['planned_inspection_date'], '2026-08-17')
        self.assertEqual(rows[0]['data']['source_status'], '待抽样')

    def test_missing_header_formula_and_broken_file_are_rejected(self):
        from sampling.services.task_excel import parse_task_workbook
        formula_row = VALUES.copy()
        formula_row[10] = '=1+1'
        for file in [upload(headers=['备注'], rows=[['无订单']]), upload(rows=[formula_row]), SimpleUploadedFile('bad.xlsx', b'broken')]:
            with self.subTest(file=file.name), self.assertRaises(ValueError):
                parse_task_workbook(file)

    def test_only_fully_identical_rows_are_skipped(self):
        from sampling.services.task_excel import parse_task_workbook, commit_rows
        rows = parse_task_workbook(upload())
        created, skipped = commit_rows(rows, self.group, self.admin)
        self.assertEqual((len(created), skipped), (1, 0))
        task = created[0]
        self.assertEqual(task.status, SamplingTask.Status.DRAFT)
        self.assertEqual(task.category_name, '水泥拉盘')
        self.assertEqual(task.notes, '备注')
        self.assertIsNone(task.sample_quantity)
        self.assertEqual(task.source_metadata['source_status'], '待抽样')
        self.assertEqual(commit_rows(rows, self.group, self.admin)[1], 1)
        for field, value in [('inspection_type', '集团检测'), ('notes', '新备注'), ('category_name', '新品类'), ('source_status', '未检查'), ('source_sequence', '2')]:
            changed = parse_task_workbook(upload())
            changed[0]['data'][field] = value
            self.assertEqual(len(commit_rows(changed, self.group, self.admin)[0]), 1, field)
        task.notes = '后续修改'
        task.save()
        self.assertEqual(len(commit_rows(rows, self.group, self.admin)[0]), 1)

    def test_invalid_kept_row_blocks_entire_batch(self):
        from sampling.services.task_excel import parse_task_workbook, commit_rows
        rows = parse_task_workbook(upload(rows=[VALUES, VALUES]))
        rows[1]['data']['draw_count'] = '-1'
        with self.assertRaises(ValueError):
            commit_rows(rows, self.group, self.admin)
        self.assertEqual(SamplingTask.objects.count(), 0)

    def test_within_file_duplicate_skipped_but_different_types_kept(self):
        from sampling.services.task_excel import parse_task_workbook, commit_rows
        other = VALUES.copy()
        other[1] = '集团检测'
        created, skipped = commit_rows(parse_task_workbook(upload(rows=[VALUES, VALUES, other])), self.group, self.admin)
        self.assertEqual((len(created), skipped), (2, 1))
