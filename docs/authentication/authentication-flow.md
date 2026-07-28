# Authentication Flow

## End-to-End Flow

```mermaid
sequenceDiagram
    participant Client
    participant API as FastAPI Auth Router
    participant OAuth as OAuthService
    participant Auth as AuthService
    participant Repo as AuthRepository
    participant DB as SQL Server
    participant JWT as JWT Helpers

    Client->>API: GET /auth/google or /auth/github
    API->>OAuth: generate signed state
    API-->>Client: 302 redirect + state cookie
    Client->>API: GET /auth/provider/callback?code&state
    API->>OAuth: validate state equality, signature, and TTL
    API->>OAuth: exchange_code_for_identity()
    OAuth-->>API: OAuthUserIdentity
    API->>Auth: authenticate_oauth_user()
    Auth->>Repo: register_oauth_user()
    Repo->>DB: sp_RegistrarOAuthUsuario
    DB-->>Repo: canonical user id
    Auth->>Repo: provision_database(user id)
    Repo->>DB: sp_AprovisionarBaseDatos
    Auth->>JWT: create_access_token()
    JWT-->>Auth: signed access token
    Auth-->>API: AccessTokenResponse
    API-->>Client: 200 bearer token
```

## Authorization Flow

Protected endpoints use `get_current_token()`, `get_current_subject()`, or `get_current_user()`. These dependencies validate the bearer token with `decode_access_token()` and return typed request context. Business authorization still belongs in SQL Server-backed procedures or explicit route-level policy dependencies.
