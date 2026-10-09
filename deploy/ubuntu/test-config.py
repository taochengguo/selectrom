"""Check deployment templates before installing them on Ubuntu."""

from pathlib import Path
import unittest


HERE = Path(__file__).resolve().parent


class UbuntuTemplateTests(unittest.TestCase):
    def test_service_is_local_and_unprivileged(self):
        service = (HERE / "selectrom.service").read_text(encoding="utf-8")
        self.assertIn("User=selectrom", service)
        self.assertIn("Group=www-data", service)
        self.assertIn("--bind 127.0.0.1:8000", service)
        self.assertIn("EnvironmentFile=/etc/selectrom/selectrom.env", service)
        self.assertNotIn("0.0.0.0:8000", service)

    def test_nginx_serves_only_expected_paths(self):
        nginx = (HERE / "selectrom.nginx.conf").read_text(encoding="utf-8")
        for expected in (
            "listen 443 ssl",
            "ssl_certificate /etc/selectrom/tls/ip.crt",
            "ssl_certificate_key /etc/selectrom/tls/ip.key",
            "alias /opt/selectrom/current/staticfiles/",
            "alias /opt/selectrom/shared/media/",
            "proxy_pass http://127.0.0.1:8000",
            "proxy_set_header Host $http_host",
            "proxy_set_header X-Forwarded-Proto https",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, nginx)
        self.assertNotIn("proxy_pass http://0.0.0.0", nginx)

    def test_certificate_has_ip_san_and_private_key_permissions(self):
        script = (HERE / "generate-ip-certificate.sh").read_text(encoding="utf-8")
        self.assertIn('subjectAltName=IP:${PUBLIC_IP}', script)
        self.assertIn('chmod 600 "${CERT_DIR}/ip.key"', script)
        self.assertIn('chmod 644 "${CERT_DIR}/ip.crt"', script)


if __name__ == "__main__":
    unittest.main()
