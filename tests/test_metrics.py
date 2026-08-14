from fastapi.testclient import TestClient

from app.main import app
from app.metrics.api.metrics_routes import get_metrics_service
from app.metrics.services.metrics_service import MetricsService


class FakeMetricsRepository:
    def __init__(self, row: dict) -> None:
        self._row = row

    def get_public_metrics(self) -> dict:
        return self._row


def _client(row: dict) -> TestClient:
    app.dependency_overrides[get_metrics_service] = lambda: MetricsService(
        repository=FakeMetricsRepository(row)
    )
    return TestClient(app)


def teardown_function() -> None:
    app.dependency_overrides.clear()


def test_get_public_metrics_requires_no_auth_and_matches_frontend_contract() -> None:
    # Exact camelCase keys expected by frontend-landing's PublicMetrics
    # TypeScript type (apps/landing/lib/api/types.ts) -- no Authorization
    # header at all, since this backs the pre-login landing page.
    client = _client(
        {
            "total_usuarios": 7,
            "total_bases_datos": 12,
            "bases_datos_activas": 3,
            "total_logins": 33,
            "usuarios_activos": 6,
            "disponibilidad": 79.66,
        }
    )

    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.json() == {
        "totalUsers": 7,
        "totalDatabases": 12,
        "activeDatabases": 3,
        "totalLogins": 33,
        "activeUsers": 6,
        "availability": 79.66,
    }


def test_get_public_metrics_defaults_missing_fields_to_zero() -> None:
    client = _client({})

    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.json()["totalUsers"] == 0
    assert response.json()["availability"] == 0.0
