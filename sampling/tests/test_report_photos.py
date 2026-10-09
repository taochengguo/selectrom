from pathlib import Path
from tempfile import TemporaryDirectory
from io import BytesIO

from PIL import Image

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from sampling.models import SamplingPhoto
from sampling.services.drawing import draw_materials
from sampling.tests.factories import SamplingFixturesMixin


class ReportPhotoTests(SamplingFixturesMixin, TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings_override = override_settings(SAMPLING_PHOTOS_ROOT=Path(self.temp.name))
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.task, self.sampler, _ = self.make_assigned_task()
        self.client.force_login(self.sampler)
        self.batch = draw_materials(task_id=self.task.pk, actor=self.sampler)
        self.url = reverse("mobile:task-report-photos", args=[self.task.pk, self.batch.pk])

    def photo(self):
        buffer = BytesIO()
        Image.new("RGB", (1, 1), "blue").save(buffer, format="PNG")
        return SimpleUploadedFile("test.png", buffer.getvalue(), content_type="image/png")

    def test_upload_persists_path_and_is_visible_after_reload(self):
        response = self.client.post(self.url, {"photo": self.photo()})
        self.assertEqual(response.status_code, 201)
        photo = SamplingPhoto.objects.get()
        self.assertTrue((Path(self.temp.name) / photo.path).is_file())
        self.assertContains(self.client.get(reverse("mobile:task-detail", args=[self.task.pk])), response.json()["photo"]["url"])
        image_response = self.client.get(response.json()["photo"]["url"])
        self.assertEqual(image_response.status_code, 200)
        image_response.close()

    def test_limit_and_delete(self):
        for _ in range(3):
            self.assertEqual(self.client.post(self.url, {"photo": self.photo()}).status_code, 201)
        self.assertEqual(self.client.post(self.url, {"photo": self.photo()}).status_code, 400)
        photo = SamplingPhoto.objects.first()
        delete_url = reverse("mobile:task-report-photo-delete", args=[self.task.pk, self.batch.pk, photo.pk])
        self.assertEqual(self.client.post(delete_url).status_code, 200)
        self.assertEqual(SamplingPhoto.objects.count(), 2)
        self.assertFalse((Path(self.temp.name) / photo.path).exists())

    def test_rejects_non_image(self):
        response = self.client.post(self.url, {"photo": SimpleUploadedFile("bad.png", b"bad", content_type="image/png")})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(SamplingPhoto.objects.count(), 0)
