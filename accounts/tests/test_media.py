import importlib
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import clear_url_caches, reverse
from PIL import Image

from accounts.models import User
from config import urls as root_urls


class DebugMediaServingTests(TestCase):
    def setUp(self):
        self.sampler = User.objects.create_user(
            "avatar_sampler",
            role=User.Role.SAMPLER,
            password="avatar-password",
        )
        self.client.force_login(self.sampler)

    def test_uploaded_profile_avatar_is_fetchable_in_debug(self):
        image_buffer = BytesIO()
        Image.new("RGB", (2, 2), color="blue").save(image_buffer, format="PNG")
        image_bytes = image_buffer.getvalue()

        response = self.client.post(
            reverse("mobile:profile"),
            {
                "action": "update_profile",
                "first_name": "Avatar",
                "avatar": SimpleUploadedFile(
                    "debug-avatar.png", image_bytes, content_type="image/png"
                ),
            },
        )
        self.sampler.refresh_from_db()
        avatar_storage = self.sampler.avatar.storage
        avatar_name = self.sampler.avatar.name
        if avatar_name:
            self.addCleanup(avatar_storage.delete, avatar_name)
        self.assertRedirects(response, reverse("mobile:profile"))

        try:
            with self.settings(DEBUG=True):
                importlib.reload(root_urls)
                clear_url_caches()
                avatar_response = self.client.get(self.sampler.avatar.url)
        finally:
            importlib.reload(root_urls)
            clear_url_caches()

        self.assertEqual(avatar_response.status_code, 200)
        self.assertEqual(b"".join(avatar_response.streaming_content), image_bytes)
