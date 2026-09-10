"""``GET /health`` tests: process/API liveness only - never calls
``create_advisory``, never touches MT5/Binance/OpenAI/the calendar bridge."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.main import create_app
from tests.api_support import FakeApplicationAdvisoryService


def test_health_returns_200_with_exact_body() -> None:
    fake = FakeApplicationAdvisoryService()
    app = create_app(service=fake)
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_never_calls_create_advisory() -> None:
    fake = FakeApplicationAdvisoryService()
    app = create_app(service=fake)
    with TestClient(app) as client:
        client.get("/health")
        client.get("/health")
    assert fake.create_advisory_calls == []


def test_health_semantic_is_process_liveness_not_provider_health() -> None:
    """Chosen V1 semantic (pre-commit security/lifespan review, "8. /HEALTH
    SEMANTICS"): /health means "the FastAPI process/lifespan is up", never
    "MT5/Binance/OpenAI are reachable". The route makes no service call at
    all (see test_health_never_calls_create_advisory above) - so once the
    process is running, /health reports 200 regardless of what the injected
    ApplicationAdvisoryService would say about any provider. If production
    startup itself fails (see tests/test_api_lifespan.py), the server never
    becomes ready and /health is naturally unreachable - that is the
    accepted, documented consequence, not a separate provider-health
    check."""
    fake = FakeApplicationAdvisoryService()
    app = create_app(service=fake)
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
