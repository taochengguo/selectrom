import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class HeroCssContractTests(SimpleTestCase):
    def test_hero_background_rule_outranks_generic_section_background(self):
        css = Path(settings.BASE_DIR, "static", "css", "mobile.css").read_text(
            encoding="utf-8"
        )

        match = re.search(
            r"\.mobile-main\s*>\s*\.mobile-hero\s*\{(?P<body>[^}]*)\}",
            css,
        )
        self.assertIsNotNone(match)
        rule = match.group("body")
        self.assertIn("background-position: 36px center", rule)
        self.assertIn("background-size: cover", rule)
