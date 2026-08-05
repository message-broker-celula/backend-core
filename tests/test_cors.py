from fastapi.testclient import TestClient

from app.main import app


def test_cors_allows_localhost_and_loopback_origins_for_preflight_requests() -> None:
    client = TestClient(app)

    response = client.options(
        "/health",
        headers={
            "origin": "http://127.0.0.1:3000",
            "access-control-request-method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:3000"

    response = client.options(
        "/auth/google",
        headers={
            "origin": "http://localhost:8000",
            "access-control-request-method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:8000"
