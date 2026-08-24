from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class FaviconContractTests(SimpleTestCase):
    def test_login_page_declares_existing_favicon_asset(self):
        response = self.client.get("/login/")

        self.assertContains(
            response,
            '<link rel="icon" href="/static/img/sampling-hero.png">',
            html=True,
        )
        self.assertTrue(
            Path(settings.BASE_DIR, "static", "img", "sampling-hero.png").is_file()
        )
