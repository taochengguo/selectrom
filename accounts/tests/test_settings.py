import os
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase


class ProductionSecretKeyTests(SimpleTestCase):
    project_root = Path(__file__).resolve().parents[2]

    def test_production_settings_fail_without_an_explicit_secret_key(self):
        result = self._import_settings(debug=False)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DJANGO_SECRET_KEY", result.stderr)

    def test_debug_settings_keep_the_local_development_fallback(self):
        result = self._import_settings(debug=True)

        self.assertEqual(result.returncode, 0, result.stderr)

    def _import_settings(self, *, debug):
        environment = os.environ.copy()
        environment["DJANGO_DEBUG"] = "true" if debug else "false"
        environment["DJANGO_SECRET_KEY"] = ""
        return subprocess.run(
            [sys.executable, "-c", "import config.settings"],
            cwd=self.project_root,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
