from django.test import TestCase
from django.urls import reverse
from urllib.parse import urlencode

from accounts.models import User
from personnel.models import PersonnelGroup
from sampling.models import SamplingTask
from sampling.tests.test_task_excel import upload, VALUES


class ExcelImportViewsTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user('import-admin', role=User.Role.ADMIN)
        self.group = PersonnelGroup.objects.create(name='预览组', created_by=self.admin)
        self.client.force_login(self.admin)

    def start(self, rows=None):
        self.url = reverse('management:task-excel-import')
        response = self.client.post(self.url, {'action': 'upload', 'file': upload(rows=rows), 'personnel_group': self.group.pk})
        self.assertEqual(response.status_code, 302)
        preview = self.client.get(response.url)
        self.assertEqual(preview.status_code, 200)
        return preview

    def payload(self, response, action='confirm'):
        data = {'token': response.context['token'], 'action': action, 'personnel_group': self.group.pk}
        for index, row in enumerate(response.context['rows']):
            for field in row['form']:
                data[f'row-{index}-{field.name}'] = field.value() or ''
        return data

    def test_preview_edits_and_deletion_apply_only_at_confirmation(self):
        preview = self.start(rows=[VALUES, VALUES])
        self.assertEqual(SamplingTask.objects.count(), 0)
        self.assertContains(preview, 'row-0-purchase_order_number')
        payload = self.payload(preview)
        payload['row-0-draw_count'] = '3'
        payload['row-0-notes'] = '已核实'
        payload['row-1-delete'] = '1'
        response = self.client.post(self.url, payload)
        self.assertRedirects(response, reverse('management:task-list'))
        task = SamplingTask.objects.get()
        self.assertEqual((task.draw_count, task.notes), (3, '已核实'))
        again = self.client.post(self.url, payload)
        self.assertEqual(again.status_code, 200)
        self.assertEqual(SamplingTask.objects.count(), 1)

    def test_validation_keeps_edits_and_does_not_partially_write(self):
        preview = self.start(rows=[VALUES, VALUES])
        payload = self.payload(preview)
        payload['row-1-draw_count'] = '0'
        response = self.client.post(self.url, payload)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['can_confirm'])
        self.assertEqual(SamplingTask.objects.count(), 0)
        self.assertContains(response, 'row-1-draw_count')
        payload['row-1-delete'] = '1'
        response = self.client.post(self.url, payload)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(SamplingTask.objects.count(), 1)

    def test_revalidate_updates_duplicates_after_edit(self):
        preview = self.start(rows=[VALUES, VALUES])
        self.assertEqual(preview.context['duplicate_count'], 1)
        payload = self.payload(preview, 'validate')
        payload['row-1-inspection_type'] = '集团检测'
        result = self.client.post(self.url, payload)
        self.assertEqual(result.context['duplicate_count'], 0)
        self.assertEqual(SamplingTask.objects.count(), 0)

    def test_preview_token_is_scoped_to_session_and_role(self):
        preview = self.start()
        payload = self.payload(preview)
        other = User.objects.create_user('other-admin', role=User.Role.ADMIN)
        self.client.force_login(other)
        response = self.client.post(self.url, payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(SamplingTask.objects.count(), 0)
        sampler = User.objects.create_user('excel-sampler', role=User.Role.SAMPLER)
        self.client.force_login(sampler)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_large_valid_chinese_preview_can_be_revalidated(self):
        row = VALUES.copy()
        row[6] = '供' * 100
        row[8] = '物' * 100
        row[16] = '址' * 200
        row[18] = '详' * 200
        preview = self.start(rows=[row] * 500)
        payload = self.payload(preview, 'validate')
        response = self.client.post(self.url, urlencode(payload), content_type='application/x-www-form-urlencoded')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['rows']), 500)

    def test_modal_upload_and_preview_return_fragment_and_confirm_returns_redirect(self):
        url = reverse('management:task-excel-import')
        initial = self.client.get(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertTemplateUsed(initial, 'management/tasks/_excel_import_content.html')
        self.assertNotContains(initial, '<html')
        uploaded = self.client.post(url, {'action': 'upload', 'file': upload(), 'personnel_group': self.group.pk}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        preview = self.client.get(uploaded.url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertTemplateUsed(preview, 'management/tasks/_excel_import_content.html')
        result = self.client.post(url, self.payload(preview), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(result.json()['redirect'], reverse('management:task-list'))
        self.assertEqual(SamplingTask.objects.count(), 1)
