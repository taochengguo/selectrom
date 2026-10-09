import os
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase


BASE_DIR = Path(__file__).resolve().parents[2]


class DeploymentSettingsTests(SimpleTestCase):
    def _settings(self, **values):
        environment = os.environ.copy()
        environment.update(
            DJANGO_DEBUG="false",
            DJANGO_SECRET_KEY="test-only-secret-key",
            DJANGO_ALLOWED_HOSTS="113.250.177.180",
            DJANGO_TRUST_PROXY_HTTPS="false",
            DJANGO_CSRF_TRUSTED_ORIGINS="",
            DJANGO_SECURE_COOKIES="false",
        )
        environment.update(values)
        script = (
            "from config import settings; "
            "print(settings.STATIC_ROOT); "
            "print(settings.MEDIA_URL); "
            "print(settings.SECURE_PROXY_SSL_HEADER); "
            "print(settings.CSRF_TRUSTED_ORIGINS); "
            "print(settings.SESSION_COOKIE_SECURE); "
            "print(settings.CSRF_COOKIE_SECURE)"
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=BASE_DIR,
            env=environment,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.splitlines()

    def test_development_proxy_settings_are_disabled(self):
        values = self._settings()
        self.assertEqual(values[0], str(BASE_DIR / "staticfiles"))
        self.assertEqual(values[1], "/media/")
        self.assertEqual(values[2], "None")
        self.assertEqual(values[3], "[]")
        self.assertEqual(values[4:], ["False", "False"])

    def test_explicit_production_proxy_settings(self):
        values = self._settings(
            DJANGO_TRUST_PROXY_HTTPS="true",
            DJANGO_CSRF_TRUSTED_ORIGINS="https://113.250.177.180",
            DJANGO_SECURE_COOKIES="true",
        )
        self.assertEqual(values[2], "('HTTP_X_FORWARDED_PROTO', 'https')")
        self.assertEqual(values[3], "['https://113.250.177.180']")
        self.assertEqual(values[4:], ["True", "True"])
