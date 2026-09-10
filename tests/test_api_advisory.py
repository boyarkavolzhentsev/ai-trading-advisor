"""``POST /v1/advisory`` happy-path tests: identity passed unchanged, exact
status mapping, DEGRADED-retains-recommendation, no retry."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.main import create_app
from app.application.dto import ApplicationAdvisoryStatus
from app.core.enums.runtime_cycle import RuntimeCycleOutcome
from tests.api_support import FakeApplicationAdvisoryService, build_advisory_response, build_recommendation


def test_logical_cycle_id_passed_unchanged() -> None:
    fake = FakeApplicationAdvisoryService(result=build_advisory_response())
    app = create_app(service=fake)
    with TestClient(app) as client:
        client.post("/v1/advisory", json={"logical_cycle_id": "cycle-abc-123"})
    assert fake.create_advisory_calls == ["cycle-abc-123"]


def test_ready_status_returns_200() -> None:
    fake = FakeApplicationAdvisoryService(
        result=build_advisory_response(status=ApplicationAdvisoryStatus.READY, recommendations=(build_recommendation(),))
    )
    app = create_app(service=fake)
    with TestClient(app) as client:
        response = client.post("/v1/advisory", json={"logical_cycle_id": "cycle-1"})
    assert response.status_code == 200
    assert response.json()["status"] == "READY"
    assert len(response.json()["recommendations"]) == 1


def test_no_trade_status_returns_200() -> None:
    fake = FakeApplicationAdvisoryService(result=build_advisory_response(status=ApplicationAdvisoryStatus.NO_TRADE))
    app = create_app(service=fake)
    with TestClient(app) as client:
        response = client.post("/v1/advisory", json={"logical_cycle_id": "cycle-1"})
    assert response.status_code == 200
    assert response.json()["status"] == "NO_TRADE"


def test_degraded_status_returns_200_with_recommendation_retained() -> None:
    fake = FakeApplicationAdvisoryService(
        result=build_advisory_response(
            status=ApplicationAdvisoryStatus.DEGRADED,
            recommendations=(build_recommendation(),),
            runtime_outcome=RuntimeCycleOutcome.PARTIAL_DEGRADED,
        )
    )
    app = create_app(service=fake)
    with TestClient(app) as client:
        response = client.post("/v1/advisory", json={"logical_cycle_id": "cycle-1"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "DEGRADED"
    assert len(body["recommendations"]) == 1


def test_service_unavailable_returns_503_with_full_structured_body() -> None:
    fake = FakeApplicationAdvisoryService(result=build_advisory_response(status=ApplicationAdvisoryStatus.SERVICE_UNAVAILABLE))
    app = create_app(service=fake)
    with TestClient(app) as client:
        response = client.post("/v1/advisory", json={"logical_cycle_id": "cycle-1"})
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "SERVICE_UNAVAILABLE"
    # full AdvisoryResponse shape retained - not replaced by an ErrorResponse envelope
    assert "logical_cycle_id" in body
    assert "data_quality" in body
    assert "diagnostics" in body
    assert "explanation" in body
    assert "error" not in body


def test_exactly_one_create_advisory_call_no_retry() -> None:
    fake = FakeApplicationAdvisoryService(result=build_advisory_response())
    app = create_app(service=fake)
    with TestClient(app) as client:
        client.post("/v1/advisory", json={"logical_cycle_id": "cycle-1"})
    assert len(fake.create_advisory_calls) == 1
