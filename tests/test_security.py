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


class SettingsTests(TestCase):
    def test_database_connection_string_is_built_from_separated_env_vars(self):
        env = {
            "SQLSERVER_DRIVER": "ODBC Driver 18 for SQL Server",
            "SQLSERVER_HOST": "sql.example.com",
            "SQLSERVER_PORT": "1444",
            "SQLSERVER_DATABASE": "MessageBrokerDB",
            "SQLSERVER_USER": "app_backend",
            "SQLSERVER_PASSWORD": "secret",
            "SQLSERVER_ENCRYPT": "yes",
            "SQLSERVER_TRUST_SERVER_CERTIFICATE": "no",
            "SQLSERVER_CONNECTION_STRING": "",
        }

        with patch.dict(os.environ, env, clear=True):
            config = importlib.import_module("app.core.config")
            config = importlib.reload(config)
            connection_string = config.Settings().database.connection_string.get_secret_value()

        self.assertEqual(
            connection_string,
            "DRIVER={ODBC Driver 18 for SQL Server};"
            "SERVER=sql.example.com,1444;"
            "DATABASE=MessageBrokerDB;"
            "UID=app_backend;"
            "PWD=secret;"
            "Encrypt=yes;"
            "TrustServerCertificate=no",
        )

    def test_database_connection_string_override_wins_when_present(self):
        env = {
            "SQLSERVER_CONNECTION_STRING": "DRIVER={Custom};SERVER=db;DATABASE=x;UID=u;PWD=p",
            "SQLSERVER_HOST": "ignored.example.com",
            "SQLSERVER_PASSWORD": "ignored",
        }

        with patch.dict(os.environ, env, clear=True):
            config = importlib.import_module("app.core.config")
            config = importlib.reload(config)
            connection_string = config.Settings().database.connection_string.get_secret_value()

        self.assertEqual(
            connection_string,
            "DRIVER={Custom};SERVER=db;DATABASE=x;UID=u;PWD=p",
        )

    def test_default_sqlserver_user_is_app_backend(self):
        """The DENY-on-tables / GRANT-on-SPs boundary only holds if the
        backend actually connects as app_backend, not an admin/db_owner
        account -- see 08_seguridad_permisos.sql / 17_fix_app_backend.sql.
        """

        with patch.dict(os.environ, {}, clear=True):
            config = importlib.import_module("app.core.config")
            config = importlib.reload(config)
            settings = config.Settings()

        self.assertEqual(settings.sqlserver_user, "app_backend")

    def test_cors_settings_are_loaded_from_env(self):
        env = {
            "CORS_ALLOWED_ORIGINS": "http://localhost:3000, https://app.example.com",
            "CORS_ALLOW_CREDENTIALS": "true",
            "CORS_ALLOWED_METHODS": "GET,POST,OPTIONS",
            "CORS_ALLOWED_HEADERS": "Authorization,Content-Type,X-Request-ID",
        }

        with patch.dict(os.environ, env, clear=True):
            config = importlib.import_module("app.core.config")
            config = importlib.reload(config)
            cors = config.Settings().cors

        self.assertEqual(
            cors.allowed_origins,
            ["http://localhost:3000", "https://app.example.com"],
        )
        self.assertTrue(cors.allow_credentials)
        self.assertEqual(cors.allowed_methods, ["GET", "POST", "OPTIONS"])
        self.assertEqual(
            cors.allowed_headers,
            ["Authorization", "Content-Type", "X-Request-ID"],
        )

    def test_root_domain_is_configurable(self):
        env = {"APP_ROOT_DOMAIN": "custom.example"}

        with patch.dict(os.environ, env, clear=True):
            config = importlib.import_module("app.core.config")
            config = importlib.reload(config)
            settings = config.Settings()

        self.assertEqual(settings.app.root_domain, "custom.example")
