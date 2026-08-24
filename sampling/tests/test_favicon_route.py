from django.test import SimpleTestCase


class FaviconRouteTests(SimpleTestCase):
    def test_root_favicon_redirects_to_existing_sampling_asset(self):
        response = self.client.get("/favicon.ico")

        self.assertRedirects(
            response,
            "/static/img/sampling-hero.png",
            status_code=302,
            fetch_redirect_response=False,
        )
