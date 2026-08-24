import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class MobileDashboardDensityTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.css = Path(
            settings.BASE_DIR, "static", "css", "mobile.css"
        ).read_text(encoding="utf-8")

    def test_dashboard_hero_matches_compact_reference_proportions(self):
        hero = re.search(
            r"\.mobile-main\s*>\s*\.mobile-hero\s*\{(?P<body>[^}]*)\}",
            self.css,
        ).group("body")

        self.assertIn("min-height: 108px", hero)
        self.assertIn("background-position: 36px center", hero)

    def test_common_phone_width_uses_four_summary_columns(self):
        common_phone = re.search(
            r"@media\s*\(min-width:\s*360px\)\s*\{(?P<body>.*?)\n\}",
            self.css,
            re.DOTALL,
        )

        self.assertIsNotNone(common_phone)
        self.assertIn(
            "grid-template-columns: repeat(4, minmax(0, 1fr))",
            common_phone.group("body"),
        )

    def test_dashboard_summary_card_has_compact_spacing(self):
        self.assertIn(
            ".mobile-main > .mobile-hero + .mobile-card {",
            self.css,
        )
        self.assertIn(
            ".mobile-main > .mobile-hero + .mobile-card .summary-item dd {",
            self.css,
        )
