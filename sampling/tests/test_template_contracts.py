import re
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import SimpleTestCase


def _custom_property(css, name):
    match = re.search(rf"{re.escape(name)}\s*:\s*(#[0-9a-fA-F]{{6}})", css)
    if match is None:
        raise AssertionError(f"Missing CSS custom property: {name}")
    return match.group(1)


def _selector_color(css, selector, tokens):
    block_match = re.search(
        rf"{re.escape(selector)}\s*\{{(?P<body>.*?)\}}", css, re.DOTALL
    )
    if block_match is None:
        raise AssertionError(f"Missing CSS selector: {selector}")
    color_match = re.search(r"(?:^|\n)\s*color\s*:\s*([^;]+)", block_match.group("body"))
    if color_match is None:
        raise AssertionError(f"Missing color declaration for: {selector}")
    value = color_match.group(1).strip()
    variable_match = re.fullmatch(r"var\((--[-a-z0-9]+)\)", value)
    return _custom_property(tokens, variable_match.group(1)) if variable_match else value


def _relative_luminance(hex_color):
    channels = [int(hex_color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        channel / 12.92
        if channel <= 0.04045
        else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast_ratio(foreground, background):
    lighter, darker = sorted(
        (_relative_luminance(foreground), _relative_luminance(background)),
        reverse=True,
    )
    return (lighter + 0.05) / (darker + 0.05)


class TemplateContractTests(SimpleTestCase):
    def read_project_file(self, relative_path):
        return (Path(settings.BASE_DIR) / relative_path).read_text(encoding="utf-8")

    def test_shared_tokens_cover_reference_palette_spacing_and_touch_target(self):
        css = self.read_project_file("static/css/tokens.css")

        for token in (
            "--color-primary",
            "--color-text",
            "--color-text-muted",
            "--color-success",
            "--color-warning",
            "--color-accent-purple",
            "--color-surface-page",
            "--color-surface-card",
            "--color-border",
            "--gradient-primary",
            "--shadow-card",
            "--radius-sm",
            "--radius-md",
            "--radius-lg",
            "--space-1",
            "--space-6",
            "--interactive-min-size: 44px",
        ):
            with self.subTest(token=token):
                self.assertIn(token, css)

    def test_small_muted_text_and_inactive_navigation_meet_wcag_aa(self):
        tokens = self.read_project_file("static/css/tokens.css")
        mobile = self.read_project_file("static/css/mobile.css")
        muted = _custom_property(tokens, "--color-text-muted")
        card = _custom_property(tokens, "--color-surface-card")
        page = _custom_property(tokens, "--color-surface-page")
        inactive_nav = _selector_color(mobile, ".mobile-tab", tokens)

        combinations = (
            ("muted text on cards", muted, card),
            ("muted text on page background", muted, page),
            ("inactive mobile navigation on white", inactive_nav, card),
        )
        for label, foreground, background in combinations:
            with self.subTest(label=label):
                self.assertGreaterEqual(
                    _contrast_ratio(foreground, background),
                    4.5,
                    f"{label} must meet WCAG AA for normal text",
                )

    def test_mobile_shell_loads_shared_styles_and_has_three_required_tabs(self):
        html = self.read_project_file("templates/mobile/base.html")

        self.assertIn("css/tokens.css", html)
        self.assertIn("css/mobile.css", html)
        self.assertIn('class="mobile-shell"', html)
        self.assertIn('class="mobile-bottom-nav"', html)
        self.assertEqual(html.count('class="mobile-tab'), 3)
        for label in ("随机抽样", "任务提醒", "个人中心"):
            with self.subTest(label=label):
                self.assertIn(label, html)

    def test_mobile_dashboard_uses_real_hero_asset_and_live_summary_data(self):
        html = self.read_project_file("templates/mobile/dashboard.html")

        self.assertIn("img/sampling-hero.png", html)
        self.assertIn('class="mobile-hero"', html)
        self.assertIn('class="summary-grid"', html)
        self.assertIn("{{ summary.total }}", html)
        self.assertIn("{{ summary.completed }}", html)
        self.assertIsNotNone(finders.find("img/sampling-hero.png"))

    def test_mobile_draw_hooks_are_preserved_inside_responsive_components(self):
        detail = self.read_project_file("templates/mobile/task_detail.html")
        results = self.read_project_file("templates/mobile/draw_result.html")

        for hook in (
            'id="sampling-reel"',
            'id="sampling-error"',
            'id="draw-form"',
            'id="draw-trigger"',
        ):
            with self.subTest(hook=hook):
                self.assertIn(hook, detail)
        self.assertIn("sampling-stage", detail)
        self.assertIn('id="sampling-results"', results)
        self.assertIn('class="result-grid"', results)

    def test_management_shell_loads_shared_styles_and_landmarks(self):
        html = self.read_project_file("templates/management/base.html")

        self.assertIn("css/tokens.css", html)
        self.assertIn("css/management.css", html)
        self.assertIn('class="management-shell"', html)
        self.assertIn('class="management-sidebar"', html)
        self.assertIn('class="management-topbar"', html)
        self.assertIn('class="management-content"', html)

    def test_management_tables_have_local_responsive_overflow_containers(self):
        table_templates = (
            "templates/management/dashboard.html",
            "templates/management/tasks/list.html",
            "templates/management/tasks/detail.html",
            "templates/management/users/list.html",
            "templates/management/logs/list.html",
        )

        for template in table_templates:
            with self.subTest(template=template):
                html = self.read_project_file(template)
                self.assertEqual(html.count('<div class="table-scroll">'), html.count("<table"))

    def test_login_page_uses_shared_authentication_shell(self):
        html = self.read_project_file("templates/accounts/login.html")

        self.assertIn("css/tokens.css", html)
        self.assertIn("css/management.css", html)
        self.assertIn('class="auth-shell"', html)
        self.assertIn('class="auth-card"', html)
