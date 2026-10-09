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
