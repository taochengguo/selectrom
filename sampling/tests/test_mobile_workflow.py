from django.test import TestCase
from django.urls import reverse

from sampling.models import SamplingBatch, SamplingCheckIn, SamplingPhoto, SamplingReport, SamplingTask
from sampling.tests.factories import SamplingFixturesMixin


class MobileWorkflowTests(SamplingFixturesMixin, TestCase):
    def test_steps_follow_saved_task_data(self):
        task, sampler, _ = self.make_assigned_task()
        self.client.force_login(sampler)
        detail = reverse("mobile:task-detail", args=[task.pk])
        workflow = reverse("mobile:task-workflow", args=[task.pk])

        self.assertContains(self.client.get(detail), "开始随机抽样")
        self.assertEqual(self.client.post(reverse("mobile:task-start", args=[task.pk])).status_code, 302)
        batch = SamplingBatch.objects.get(task=task)
        self.assertEqual(batch.status, SamplingBatch.Status.AUTHORIZED)
        self.assertEqual(self.client.get(workflow).context["step"], 1)
        self.assertEqual(self.client.post(reverse("mobile:task-draw", args=[task.pk])).status_code, 400)

        report = SamplingReport.objects.create(batch=batch)
        SamplingCheckIn.objects.create(report=report, status=SamplingCheckIn.Status.SAME_CITY, created_by=sampler)
        self.assertEqual(self.client.get(workflow).context["step"], 2)
        SamplingPhoto.objects.create(batch=batch, path="test/photo.png", original_name="photo.png")
        self.assertEqual(self.client.get(workflow).context["step"], 3)
        self.assertEqual(self.client.get(workflow + "?step=1").context["step"], 1)
        self.assertEqual(self.client.get(workflow + "?step=5").context["step"], 3)

        draw = self.client.post(reverse("mobile:task-draw", args=[task.pk]))
        self.assertEqual(draw.status_code, 200)
        self.assertEqual(self.client.get(workflow).context["step"], 4)
        self.assertEqual(self.client.post(reverse("mobile:task-complete", args=[task.pk])).status_code, 302)
        task.refresh_from_db()
        self.assertEqual(task.status, SamplingTask.Status.IN_PROGRESS)

        self.client.post(reverse("mobile:task-report-save", args=[task.pk, batch.pk]), {"inspection_result": "合格"})
        self.client.post(reverse("mobile:task-complete", args=[task.pk]))
        task.refresh_from_db()
        self.assertEqual(task.status, SamplingTask.Status.COMPLETED)
        self.assertEqual(self.client.get(workflow).context["step"], 5)
        completed = self.client.get(workflow + "?step=2")
        self.assertEqual(completed.context["step"], 5)
        self.assertContains(completed, "此次抽样任务详情")
        self.assertNotContains(completed, "data-sampling-report")
        self.assertNotContains(completed, 'href="?step=2"')
        detail_response = self.client.get(detail)
        self.assertContains(detail_response, "抽样报告详情")
        self.assertContains(detail_response, "导出报告")
        self.assertNotContains(detail_response, "data-report-form")
        report_url = reverse("mobile:task-report-detail", args=[task.pk])
        self.assertContains(detail_response, f'href="{report_url}"')
        report_page = self.client.get(report_url)
        self.assertContains(report_page, "任务详情")
        self.assertContains(report_page, "抽样报告详情")
        self.assertContains(report_page, "合格")
        self.assertNotContains(report_page, 'data-export-completed-report')
        self.assertNotContains(report_page, 'data-export-report')
        self.assertNotContains(report_page, 'data-report-form')
        self.assertNotContains(report_page, 'id="completed-reports" hidden')
        for name, args, data in [
            ("task-report-save", [task.pk, batch.pk], {"inspection_result": "修改"}),
            ("task-report-checkin", [task.pk, batch.pk], {"note": "修改"}),
            ("task-report-photos", [task.pk, batch.pk], {}),
            ("task-report-photo-delete", [task.pk, batch.pk, batch.photos.first().pk], {}),
        ]:
            with self.subTest(endpoint=name):
                self.assertEqual(self.client.post(reverse("mobile:" + name, args=args), data).status_code, 400)
        report.refresh_from_db()
        self.assertEqual(report.inspection_result, "合格")
        self.assertEqual(report.checkins.count(), 1)
        self.assertEqual(batch.photos.count(), 1)
