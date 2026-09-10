"""Wire-contract test: Decimal fields serialize as JSON strings (exact
precision preserved, never a float), timezone-aware datetimes serialize as
ISO-8601 - round-tripped through the real ``/v1/advisory`` route, not a
throwaway ad-hoc model. Confirms the plan already verified directly against
FastAPI/pydantic during dependency prep (see the FastAPI dependency-prep
report) holds for this application's own real response_model."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from fastapi.testclient import TestClient

from app.api.main import create_app
from app.application.dto import ApplicationAdvisoryStatus
from tests.api_support import FakeApplicationAdvisoryService, build_advisory_response, build_recommendation


def test_decimal_fields_serialize_as_json_strings_with_exact_precision() -> None:
    recommendation = build_recommendation()
    fake = FakeApplicationAdvisoryService(
        result=build_advisory_response(status=ApplicationAdvisoryStatus.READY, recommendations=(recommendation,))
    )
    with TestClient(create_app(service=fake)) as client:
        response = client.post("/v1/advisory", json={"logical_cycle_id": "cycle-1"})

    body = response.json()
    rec = body["recommendations"][0]

    for field in ("entry_price", "stop_loss", "approved_volume", "approved_risk_amount"):
        assert isinstance(rec[field], str), f"{field} must serialize as a JSON string, got {type(rec[field])}"

    assert rec["entry_price"] == "1.10000"
    assert rec["approved_volume"] == "0.50"
    assert rec["approved_risk_amount"] == "25.00"
    assert isinstance(rec["take_profit_levels"][0], str)
    assert rec["take_profit_levels"][0] == "1.12000"

    # never silently lossy: parsing back must reproduce the exact Decimal.
    assert Decimal(rec["entry_price"]) == recommendation.entry_price
    assert Decimal(rec["approved_volume"]) == recommendation.approved_volume


def test_datetime_fields_serialize_as_timezone_aware_iso8601() -> None:
    recommendation = build_recommendation()
    fake = FakeApplicationAdvisoryService(
        result=build_advisory_response(status=ApplicationAdvisoryStatus.READY, recommendations=(recommendation,))
    )
    with TestClient(create_app(service=fake)) as client:
        response = client.post("/v1/advisory", json={"logical_cycle_id": "cycle-1"})

    body = response.json()
    as_of = body["as_of"]
    signal_time = body["recommendations"][0]["signal_time"]

    for value in (as_of, signal_time):
        assert isinstance(value, str)
        assert value.endswith("Z") or "+" in value[10:] or "-" in value[10:], f"expected an explicit UTC designator, got {value!r}"
        parsed = datetime.fromisoformat(value)
        assert parsed.tzinfo is not None, "datetime must be timezone-aware, never naive"

    assert as_of == "2026-05-01T12:00:00Z"
