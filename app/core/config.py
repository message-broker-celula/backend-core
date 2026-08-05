from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseModel):
    """Application configuration."""

    name: str
    version: str
    environment: str
    debug: bool
    trusted_hosts: list[str]


class CorsSettings(BaseModel):
    """CORS configuration."""

    allowed_origins: list[str]
    allow_origin_regex: str | None
    allow_credentials: bool
    allowed_methods: list[str]
    allowed_headers: list[str]


class JWTSettings(BaseModel):
    """JWT configuration."""

    secret_key: SecretStr
    algorithm: str
    expire_minutes: int
    refresh_expire_minutes: int = 1440
    issuer: str | None = None
    audience: str | None = None


class DatabaseSettings(BaseModel):
    """Database connection configuration."""

    connection_string: SecretStr
    stored_procedure_timeout_seconds: int


class GoogleSettings(BaseModel):
    """Google OAuth configuration."""

    client_id: str
    client_secret: SecretStr
    redirect_uri: str
    authorize_url: str
    token_url: str
    userinfo_url: str


class GithubSettings(BaseModel):
    """GitHub OAuth configuration."""

    client_id: str
    client_secret: SecretStr
    redirect_uri: str
    authorize_url: str
    token_url: str
    userinfo_url: str
    emails_url: str


class OAuthSettings(BaseModel):
    """OAuth providers configuration."""

    google: GoogleSettings
    github: GithubSettings
    state_cookie_secure: bool
    state_cookie_samesite: str
    state_ttl_seconds: int


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = Field(default="Backend Core")
    app_version: str = Field(default="1.0.0")
    app_environment: str = Field(default="development")
    app_debug: bool = Field(default=True)
    app_trusted_hosts: str = Field(default="localhost,127.0.0.1,testserver")

    # CORS
    cors_allowed_origins: str = Field(default="http://localhost:3000,http://localhost:5173,http://localhost:8000,http://127.0.0.1:3000,http://127.0.0.1:5173,http://127.0.0.1:8000")
    cors_allow_origin_regex: str | None = Field(default=r"https?://(localhost|127\.0\.0\.1)(:\d+)?$")
    cors_allow_credentials: bool = Field(default=True)
    cors_allowed_methods: str = Field(default="GET,POST,PUT,PATCH,DELETE,OPTIONS")
    cors_allowed_headers: str = Field(default="Authorization,Content-Type")

    # JWT
    jwt_secret_key: str = Field(default="change-me-in-production")
    jwt_algorithm: str = Field(default="HS256")
    jwt_expire_minutes: int = Field(default=60)
    jwt_refresh_expire_minutes: int = Field(default=1440)
    jwt_issuer: str | None = Field(default=None)
    jwt_audience: str | None = Field(default=None)

    # SQL Server
    sqlserver_connection_string: str = Field(default="")
    sqlserver_driver: str = Field(default="ODBC Driver 18 for SQL Server")
    sqlserver_host: str = Field(default="localhost")
    sqlserver_port: int = Field(default=1433)
    sqlserver_database: str = Field(default="MessageBrokerDB")
    sqlserver_user: str = Field(default="app_backend")
    sqlserver_password: str = Field(default="")
    sqlserver_encrypt: str = Field(default="yes")
    sqlserver_trust_server_certificate: str = Field(default="yes")
    sqlserver_sp_timeout_seconds: int = Field(default=30)

    # Google OAuth
    google_client_id: str = Field(default="")
    google_client_secret: str = Field(default="")
    google_redirect_uri: str = Field(default="http://localhost:8000/auth/google/callback")
    google_authorize_url: str = Field(default="https://accounts.google.com/o/oauth2/v2/auth")
    google_token_url: str = Field(default="https://oauth2.googleapis.com/token")
    google_userinfo_url: str = Field(default="https://openidconnect.googleapis.com/v1/userinfo")

    # GitHub OAuth
    github_client_id: str = Field(default="")
    github_client_secret: str = Field(default="")
    github_redirect_uri: str = Field(default="http://localhost:8000/auth/github/callback")
    github_authorize_url: str = Field(default="https://github.com/login/oauth/authorize")
    github_token_url: str = Field(default="https://github.com/login/oauth/access_token")
    github_userinfo_url: str = Field(default="https://api.github.com/user")
    github_emails_url: str = Field(default="https://api.github.com/user/emails")

    # OAuth state cookie
    oauth_state_cookie_secure: bool = Field(default=True)
    oauth_state_cookie_samesite: str = Field(default="lax")
    oauth_state_ttl_seconds: int = Field(default=600)

    @property
    def app(self) -> AppSettings: 
        """Application settings."""

        trusted_hosts = [
            host.strip()
            for host in self.app_trusted_hosts.split(",")
            if host.strip()
        ]
        return AppSettings(
            name=self.app_name,
            version=self.app_version,
            environment=self.app_environment,
            debug=self.app_debug,
            trusted_hosts=trusted_hosts,
        )

    @property
    def cors(self) -> CorsSettings:
        """CORS settings."""

        return CorsSettings(
            allowed_origins=self._split_csv(self.cors_allowed_origins),
            allow_origin_regex=self.cors_allow_origin_regex,
            allow_credentials=self.cors_allow_credentials,
            allowed_methods=self._split_csv(self.cors_allowed_methods),
            allowed_headers=self._split_csv(self.cors_allowed_headers),
        )

    @property
    def jwt(self) -> JWTSettings:
        """JWT Settings."""

        return JWTSettings(
            secret_key=SecretStr(self.jwt_secret_key),
            algorithm=self.jwt_algorithm,
            expire_minutes=self.jwt_expire_minutes,
            refresh_expire_minutes=self.jwt_refresh_expire_minutes,
            issuer=self.jwt_issuer,
            audience=self.jwt_audience,
        )

    @property
    def database(self) -> DatabaseSettings:
        """Database settings."""

        connection_string = (
            self.sqlserver_connection_string.strip()
            or self._build_sqlserver_connection_string()
        )
        return DatabaseSettings(
            connection_string=SecretStr(connection_string),
            stored_procedure_timeout_seconds=self.sqlserver_sp_timeout_seconds,
        )

    def _build_sqlserver_connection_string(self) -> str:
        """Build a pyodbc SQL Server connection string from separated env vars."""

        return (
            f"DRIVER={{{self.sqlserver_driver}}};"
            f"SERVER={self.sqlserver_host},{self.sqlserver_port};"
            f"DATABASE={self.sqlserver_database};"
            f"UID={self.sqlserver_user};"
            f"PWD={self.sqlserver_password};"
            f"Encrypt={self.sqlserver_encrypt};"
            f"TrustServerCertificate={self.sqlserver_trust_server_certificate}"
        )

    @staticmethod
    def _split_csv(value: str) -> list[str]:
        """Split comma-separated env values into a clean list."""

        return [item.strip() for item in value.split(",") if item.strip()]

    @property
    def oauth(self) -> OAuthSettings:
        """OAuth providers settings."""

        return OAuthSettings(
            google=GoogleSettings(
                client_id=self.google_client_id,
                client_secret=SecretStr(self.google_client_secret),
                redirect_uri=self.google_redirect_uri,
                authorize_url=self.google_authorize_url,
                token_url=self.google_token_url,
                userinfo_url=self.google_userinfo_url,
            ),
            github=GithubSettings(
                client_id=self.github_client_id,
                client_secret=SecretStr(self.github_client_secret),
                redirect_uri=self.github_redirect_uri,
                authorize_url=self.github_authorize_url,
                token_url=self.github_token_url,
                userinfo_url=self.github_userinfo_url,
                emails_url=self.github_emails_url,
            ),
            state_cookie_secure=self.oauth_state_cookie_secure,
            state_cookie_samesite=self.oauth_state_cookie_samesite,
            state_ttl_seconds=self.oauth_state_ttl_seconds,
        )


settings = Settings()
