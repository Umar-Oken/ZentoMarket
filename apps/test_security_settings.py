import json
import os
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase


BASE_DIR = Path(__file__).resolve().parent.parent


class ProductionSettingsTests(SimpleTestCase):
    def test_production_requires_secret_key(self):
        env = {
            key: os.environ[key]
            for key in ("PATH", "SYSTEMROOT")
            if key in os.environ
        }
        env["PYTHONPATH"] = str(BASE_DIR)
        env.update(
            DJANGO_ENV="production",
            SECRET_KEY="",
            DEBUG="false",
            ALLOWED_HOSTS="shop.example.com",
        )
        result = subprocess.run(
            [sys.executable, "-c", "from root import settings"],
            check=False,
            capture_output=True,
            cwd=BASE_DIR,
            env=env,
            text=True,
            timeout=15,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SECRET_KEY must be set in production.", result.stderr)

    def test_production_defaults_enable_transport_security(self):
        env = {
            key: os.environ[key]
            for key in ("PATH", "SYSTEMROOT")
            if key in os.environ
        }
        env["PYTHONPATH"] = str(BASE_DIR)
        env.update(
            DJANGO_ENV="production",
            SECRET_KEY="test-only-production-key-" + "x" * 64,
            DEBUG="false",
            ALLOWED_HOSTS="shop.example.com",
        )
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import json; from root import settings; "
                    "print(json.dumps({"
                    "'debug': settings.DEBUG, "
                    "'hosts': settings.ALLOWED_HOSTS, "
                    "'https_redirect': settings.SECURE_SSL_REDIRECT, "
                    "'session_cookie_secure': settings.SESSION_COOKIE_SECURE, "
                    "'csrf_cookie_secure': settings.CSRF_COOKIE_SECURE, "
                    "'hsts': settings.SECURE_HSTS_SECONDS, "
                    "'email_backend': settings.EMAIL_BACKEND"
                    "}))"
                ),
            ],
            check=False,
            capture_output=True,
            cwd=BASE_DIR,
            env=env,
            text=True,
            timeout=15,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        config = json.loads(result.stdout)
        self.assertFalse(config["debug"])
        self.assertEqual(config["hosts"], ["shop.example.com"])
        self.assertTrue(config["https_redirect"])
        self.assertTrue(config["session_cookie_secure"])
        self.assertTrue(config["csrf_cookie_secure"])
        self.assertEqual(config["hsts"], 31536000)
        self.assertEqual(
            config["email_backend"],
            "django.core.mail.backends.smtp.EmailBackend",
        )
