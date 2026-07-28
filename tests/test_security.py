import importlib
import os
from unittest import TestCase
from unittest.mock import patch


class CreateAccessTokenTests(TestCase):
    def test_create_access_token_and_decode_round_trip(self):
        env = {
            "APP_NAME": "Backend Core",
            "APP_VERSION": "1.0.0",
            "APP_ENVIRONMENT": "development",
            "APP_DEBUG": "True",
            "JWT_SECRET_KEY": "test-secret-key",
            "JWT_ALGORITHM": "HS256",
            "JWT_EXPIRE_MINUTES": "60",
            "GOOGLE_CLIENT_ID": "google-client-id",
            "GOOGLE_CLIENT_SECRET": "google-client-secret",
            "GOOGLE_REDIRECT_URI": "http://localhost/google",
            "GITHUB_CLIENT_ID": "github-client-id",
            "GITHUB_CLIENT_SECRET": "github-client-secret",
            "GITHUB_REDIRECT_URI": "http://localhost/github",
        }

        with patch.dict(os.environ, env, clear=True):
            security = importlib.import_module("app.core.security")
            security = importlib.reload(security)

            token = security.create_access_token(subject="user-123")
            decoded = security.decode_access_token(token)

        self.assertIsInstance(token, str)
        self.assertEqual(decoded.sub, "user-123")
