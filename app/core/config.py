from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseModel):
    """Application configuration."""

    name: str
    version: str
    environment: str
    debug: bool
    trusted_hosts: list[str]
    root_domain: str
    frontend_url: str


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


class ProvisioningSettings(BaseModel):
    """Database engine auto-provisioning configuration.

    The provisioner is a separate sidecar service (the only process with
    /var/run/docker.sock access) that this backend calls over the internal
    docker network to create/stop/start/remove real database engine
    containers -- see provisioner/.
    """

    base_url: str
    shared_secret: SecretStr
    request_timeout_seconds: int
    public_host: str
    port_range_start: int
    port_range_end: int
    port_allocation_attempts: int
    password_length: int
    supported_engines: list[str]


class DnsSettings(BaseModel):
    """User self-service DNS subdomain configuration (Cloudflare).

    Backs `[servicio].[celula].{root_domain}` records under a domain
    separate from the platform's own APP_ROOT_DOMAIN -- see app/dns/.
    """

    cloudflare_api_token: SecretStr
    cloudflare_zone_id: str
    root_domain: str
    target_ip: str
    request_timeout_seconds: int


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
    app_root_domain: str = Field(default="andrescortes.dev")
    # Where the OAuth callback redirects the browser after issuing a token --
    # the frontend owns a route at {app_frontend_url}/auth/callback that reads
    # ?access_token=... (and ?error=... on failure) from the query string.
    app_frontend_url: str = Field(default="http://localhost:5173")

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
    # SQLSERVER_USER debe ser "app_backend": el unico usuario con EXECUTE
    # sobre los Stored Procedures/Views/Functions y DENY sobre las tablas.
    # Es lo que hace cumplir a nivel de base de datos la regla de "el
    # backend nunca hace SELECT/INSERT/UPDATE/DELETE directo" -- ver
    # 08_seguridad_permisos.sql y 17_fix_app_backend.sql.
    sqlserver_driver: str = Field(default="ODBC Driver 18 for SQL Server")
    sqlserver_host: str = Field(default="localhost")
    sqlserver_port: int = Field(default=1433)
    sqlserver_database: str = Field(default="MessageBrokerDB")
    sqlserver_user: str = Field(default="app_backend")
    sqlserver_password: str = Field(default="")
    sqlserver_encrypt: str = Field(default="yes")
    sqlserver_trust_server_certificate: str = Field(default="yes")
    sqlserver_connection_string: str = Field(default="")
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

    # Database provisioning (sidecar with the only Docker socket access --
    # see provisioner/). base_url uses the compose service name "provisioner"
    # by default since backend-core-backend reaches it over internal_net.
    provisioning_base_url: str = Field(default="http://provisioner:9000")
    provisioning_shared_secret: str = Field(default="")
    # A fresh volume means MySQL's first-boot init (not just image pull) can
    # itself take 20-30s -- confirmed in production that 45s was too tight
    # against the sidecar's own 30s readiness budget plus HTTP/creation
    # overhead, causing the client to give up on requests that actually
    # succeeded server-side moments later.
    provisioning_request_timeout_seconds: int = Field(default=90)
    # VPS's externally-reachable address (raw TCP, no nginx/TLS involved) --
    # NOT the sidecar's internal Docker hostname. Returned to end users as
    # the `host` they connect their own apps to.
    provisioning_public_host: str = Field(default="")
    provisioning_port_range_start: int = Field(default=30000)
    provisioning_port_range_end: int = Field(default=40000)
    provisioning_port_allocation_attempts: int = Field(default=5)
    provisioning_password_length: int = Field(default=24)
    provisioning_supported_engines: str = Field(default="MYSQL")

    # User self-service DNS subdomains (Cloudflare) -- [servicio].[celula].
    # {dns_root_domain}, separate from APP_ROOT_DOMAIN (the platform's own
    # domain). The token is scoped/IP-filtered to this backend's egress IP
    # in the Cloudflare dashboard, never logged, never committed.
    dns_cloudflare_api_token: str = Field(default="")
    dns_cloudflare_zone_id: str = Field(default="")
    dns_root_domain: str = Field(default="coderhivex.com")
    # VPS's externally-reachable IP -- same address as provisioning_public_host
    # conceptually, kept as its own setting since the two features are
    # otherwise unrelated (Docker provisioning vs public DNS).
    dns_target_ip: str = Field(default="")
    dns_request_timeout_seconds: int = Field(default=15)

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
            root_domain=self.app_root_domain,
            frontend_url=self.app_frontend_url.rstrip("/"),
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
        """JWT settings."""

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

    @property
    def provisioning(self) -> ProvisioningSettings:
        """Database engine provisioning settings."""

        return ProvisioningSettings(
            base_url=self.provisioning_base_url.rstrip("/"),
            shared_secret=SecretStr(self.provisioning_shared_secret),
            request_timeout_seconds=self.provisioning_request_timeout_seconds,
            public_host=self.provisioning_public_host,
            port_range_start=self.provisioning_port_range_start,
            port_range_end=self.provisioning_port_range_end,
            port_allocation_attempts=self.provisioning_port_allocation_attempts,
            password_length=self.provisioning_password_length,
            supported_engines=self._split_csv(self.provisioning_supported_engines.upper()),
        )

    @property
    def dns(self) -> DnsSettings:
        """User self-service DNS subdomain settings."""

        return DnsSettings(
            cloudflare_api_token=SecretStr(self.dns_cloudflare_api_token),
            cloudflare_zone_id=self.dns_cloudflare_zone_id,
            root_domain=self.dns_root_domain,
            target_ip=self.dns_target_ip,
            request_timeout_seconds=self.dns_request_timeout_seconds,
        )


settings = Settings()
