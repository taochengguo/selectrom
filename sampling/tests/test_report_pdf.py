from io import BytesIO

from django.test import TestCase
from django.urls import reverse

from sampling.models import SamplingReport
from sampling.services.drawing import draw_materials, complete_task
from sampling.tests.factories import SamplingFixturesMixin


class ReportPdfTests(SamplingFixturesMixin, TestCase):
    def setUp(self):
        self.task, self.sampler, _ = self.make_assigned_task()
        self.batch = draw_materials(task_id=self.task.pk, actor=self.sampler)
        SamplingReport.objects.create(batch=self.batch, inspection_result="检测合格 <正常>")
        complete_task(task_id=self.task.pk, actor=self.sampler)
        self.client.force_login(self.sampler)

    def test_download_is_pdf_attachment(self):
        url = reverse("mobile:task-report-pdf", args=[self.task.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("attachment;", response["Content-Disposition"])
        self.assertIn(".pdf", response["Content-Disposition"])
        data = b"".join(response.streaming_content)
        self.assertTrue(data.startswith(b"%PDF-"))
        self.assertTrue(data.rstrip().endswith(b"%%EOF"))
        self.assertContains(self.client.get(reverse("mobile:task-detail", args=[self.task.pk])), f'href="{url}"')

    def test_other_sampler_cannot_download(self):
        from accounts.models import User
        other = User.objects.create_user("other", role=User.Role.SAMPLER)
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse("mobile:task-report-pdf", args=[self.task.pk])).status_code, 404)

