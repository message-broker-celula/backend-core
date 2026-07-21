from pydantic import BaseModel  
from pydantic_settings import BaseSettings, SettingsConfigDict

class AppSettings(BaseModel):
    """ Application configuration. """
    name: str
    version: str 
    environment: str 
    debug: bool 

class JWTSettings(BaseModel): 
    """ JWT configuration. """
    secret_key: str
    algorithm: str
    expire_minutes: int 

class GoogleSettings(BaseModel): 
    """ Google OAuth configuration. """
    client_id: str
    client_secret: str
    redirect_uri: str

class GithubSettings(BaseModel): 
    """ GitHub OAuth configuration. """
    client_id: str
    client_secret: str
    redirect_uri: str 

class OAuthSettings(BaseModel): 
    """ OAuth providers configuration. """
    google: GoogleSettings
    github: GithubSettings

class DataBaseSettings(BaseModel): 
    """ Database configuration. """
    host: str
    port: int
    database: str
    username: str
    password: str

class Settings(BaseSettings):
    """ Application settings. """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False, 
        extra="ignore",
    )

        # Application
    app_name: str
    app_version: str
    app_environment: str
    app_debug: bool

    # JWT
    jwt_secret_key: str
    jwt_algorithm: str
    jwt_expire_minutes: int

    # Google OAuth
    google_client_id: str
    google_client_secret: str
    google_redirect_uri: str

    # GitHub OAuth
    github_client_id: str
    github_client_secret: str
    github_redirect_uri: str

    @property
    def app(self) -> AppSettings: 
        """Application settings."""

        return AppSettings( 
            name =self.app_name, 
            version=self.app_version, 
            environment=self.app_environment,
            debug=self.app_debug,
        )
    
    @property 
    def jwt(self) -> JWTSettings: 
        """JWT Settings."""

        return JWTSettings(
            secret_keY=self.jwt_secret_key, 
            algorithm=self.jwt_algorithm, 
            expire_minutes=self.jwt_expire_minutes, 
        )
    
    @property 
    def oauth(self) -> OAuthSettings: 
        """OAuth providers settings."""

        return OAuthSettings(
            google=GithubSettings(
                client_id=self.google_client_id,
                client_secret=self.google_client_secret,
                redirect_uri=self.google_redirect_uri,
            ),
            gituhb=GithubSettings(
                client_id=self.github_client_id,
                client_secret=self.github_client_secret,
                redirect_uri=self.github_redirect_uri,
            ),
        )
    