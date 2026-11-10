from io import BytesIO
from zipfile import ZipFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from sampling.tests.test_report_pdf import ReportPdfTests
from sampling.services.report_pdf import report_filename
from accounts.models import User


class ManagementReportTests(ReportPdfTests):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_user('report_admin', role='admin')
        self.client.force_login(self.admin)
        self.task.purchase_order_number = '采购/123'
        self.task.save(update_fields=['purchase_order_number'])

    def test_preview_and_zip_names(self):
        url = reverse('management:task-report',args=[self.task.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code,200)
        self.assertIn('inline;',response['Content-Disposition'])
        self.assertTrue(b''.join(response.streaming_content).startswith(b'%PDF-'))
        response = self.client.post(reverse('management:task-reports-export'),{'tasks':[self.task.pk]})
        self.assertEqual(response['Content-Type'],'application/zip')
        with ZipFile(BytesIO(b''.join(response.streaming_content))) as archive:
            filename = report_filename(self.task)
            self.assertEqual(archive.namelist(),[filename])
            self.assertIn('_采购_123_',filename)
            self.assertTrue(filename.startswith(timezone.localtime(self.batch.drawn_at).strftime('%Y%m%d')))
            self.assertTrue(archive.read(filename).startswith(b'%PDF-'))

    def test_incomplete_and_invalid_selection_are_rejected(self):
        self.task.status='in_progress'
        self.task.save(update_fields=['status'])
        response=self.client.get(reverse('management:task-report',args=[self.task.pk]))
        self.assertRedirects(response,reverse('management:task-list'))
        url=reverse('management:task-reports-export')
        for values in ([self.task.pk],[],['invalid'],[999999]):
            self.assertRedirects(self.client.post(url,{'tasks':values}),reverse('management:task-list'))
        self.client.force_login(self.sampler)
        self.assertEqual(self.client.get(reverse('management:task-report',args=[self.task.pk])).status_code,403)
        self.assertEqual(self.client.post(url,{'tasks':[self.task.pk]}).status_code,403)

    # Mobile-only checks are already covered by ReportPdfTests.
    def test_download_is_pdf_attachment(self):
        self.client.force_login(self.sampler)
        super().test_download_is_pdf_attachment()
