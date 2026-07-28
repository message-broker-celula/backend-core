# Authentication Endpoints

## `GET /auth/google`

Starts Google OAuth. Returns `302 Found` with a provider redirect and sets `oauth_state_google`. The cookie contains a signed, time-bounded state token.

## `GET /auth/google/callback`

Completes Google OAuth. Returns `200 OK` with `AccessTokenResponse` or:

- `400` when the provider denies authorization or omits the code
- `401` when OAuth state validation fails
- `502` when provider token or profile validation fails
- `503` when the database-backed authentication contract is unavailable

## `GET /auth/github`

Starts GitHub OAuth. Returns `302 Found` with a provider redirect and sets `oauth_state_github`. The cookie contains a signed, time-bounded state token.

## `GET /auth/github/callback`

Completes GitHub OAuth. It has the same response contract as the Google callback. If the public GitHub profile does not include an email address, the service calls the configured GitHub emails endpoint and uses the verified primary email when present.

## `GET /auth/me`

Requires `Authorization: Bearer <token>`. Returns the authenticated subject and decoded token payload.

## `POST /auth/logout`

Clears OAuth state cookies and returns:

```json
{"detail": "Logged out"}
```

JWT access tokens are stateless and remain valid until expiration. Token revocation requires a database-backed denylist or session store contract.

## Local Credentials

`POST /auth/login` and `POST /auth/register` are not exposed. OAuth is the supported credential model for this backend until SQL Server owns explicit stored procedures for password verification, registration, lockout, and credential lifecycle policy.
