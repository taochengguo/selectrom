from django.conf import settings
from django.test import SimpleTestCase
from django.urls import reverse


class ProjectSmokeTests(SimpleTestCase):
    def test_health_route(self):
        response = self.client.get(reverse("health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_standard_auth_configuration_precedes_custom_user_app(self):
        self.assertEqual(settings.AUTH_USER_MODEL, "auth.User")
        self.assertTrue(
            {
                "django.contrib.auth",
                "django.contrib.contenttypes",
                "django.contrib.sessions",
                "django.contrib.messages",
                "django.contrib.staticfiles",
            }.issubset(settings.INSTALLED_APPS)
        )
        self.assertNotIn("accounts", settings.INSTALLED_APPS)
        self.assertIn(
            "django.contrib.auth.middleware.AuthenticationMiddleware",
            settings.MIDDLEWARE,
        )
        self.assertTrue(
            {
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            }.issubset(settings.TEMPLATES[0]["OPTIONS"]["context_processors"])
        )
