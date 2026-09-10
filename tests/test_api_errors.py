"""Error-mapping tests: input validation, duplicate, state, internal, and a
generic-exception defense-in-depth secret-leak check.

Pre-commit security review correction: ``ApplicationInputError`` and
``ApplicationStateError`` now map to fixed, content-independent HTTP
messages - never ``str(exc)`` - because ``app.application.identity.
validate_logical_cycle_id`` embeds the caller's rejected, arbitrary value
verbatim into its own exception message, and a public wire contract must
not depend on Stage0D's internal lifecycle wording either."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.main import create_app
from app.application.errors import ApplicationInputError, ApplicationStateError, DuplicateCycleError, InternalApplicationError
from tests.api_support import FakeApplicationAdvisoryService, build_advisory_response


def _client(fake: FakeApplicationAdvisoryService) -> TestClient:
    return TestClient(create_app(service=fake))


# --- input validation --------------------------------------------------


def test_missing_logical_cycle_id_returns_422() -> None:
    fake = FakeApplicationAdvisoryService(result=build_advisory_response())
    with _client(fake) as client:
        response = client.post("/v1/advisory", json={})
    assert response.status_code == 422
    assert fake.create_advisory_calls == []


def test_extra_symbol_field_returns_422() -> None:
    fake = FakeApplicationAdvisoryService(result=build_advisory_response())
    with _client(fake) as client:
        response = client.post("/v1/advisory", json={"logical_cycle_id": "cycle-1", "symbol": "BTCUSDT"})
    assert response.status_code == 422
    assert fake.create_advisory_calls == []


def test_extra_arbitrary_field_returns_422() -> None:
    fake = FakeApplicationAdvisoryService(result=build_advisory_response())
    with _client(fake) as client:
        response = client.post("/v1/advisory", json={"logical_cycle_id": "cycle-1", "anything": 123})
    assert response.status_code == 422
    assert fake.create_advisory_calls == []


def test_request_validation_error_uses_stable_sanitized_envelope() -> None:
    fake = FakeApplicationAdvisoryService(result=build_advisory_response())
    with _client(fake) as client:
        response = client.post("/v1/advisory", json={})
    body = response.json()
    assert body == {"error": {"code": "APPLICATION_INPUT_ERROR", "message": "Invalid request.", "logical_cycle_id": None, "colliding_trade_ids": []}}


def test_application_input_error_returns_422_fixed_message_not_the_rejected_value() -> None:
    fake = FakeApplicationAdvisoryService(
        create_advisory_exception=ApplicationInputError("logical_cycle_id must match [A-Za-z0-9_-]{1,128}; got 'bad:id'")
    )
    with _client(fake) as client:
        response = client.post("/v1/advisory", json={"logical_cycle_id": "bad:id"})
    assert response.status_code == 422
    body = response.json()
    assert body == {"error": {"code": "APPLICATION_INPUT_ERROR", "message": "Invalid logical_cycle_id.", "logical_cycle_id": None, "colliding_trade_ids": []}}
    assert "bad:id" not in response.text


def test_invalid_logical_cycle_id_containing_fake_secret_is_never_echoed() -> None:
    fake_secret_value = "sk-FAKE-SECRET-abcdef123456:not-a-valid-cycle-id"
    fake = FakeApplicationAdvisoryService(
        create_advisory_exception=ApplicationInputError(
            f"logical_cycle_id must match [A-Za-z0-9_-]{{1,128}}; got {fake_secret_value!r}"
        )
    )
    with _client(fake) as client:
        response = client.post("/v1/advisory", json={"logical_cycle_id": fake_secret_value})
    assert response.status_code == 422
    assert fake_secret_value not in response.text
    assert response.json()["error"]["message"] == "Invalid logical_cycle_id."


def test_very_long_invalid_logical_cycle_id_response_stays_small_and_unechoed() -> None:
    long_invalid_value = "x" * 10_000
    fake = FakeApplicationAdvisoryService(
        create_advisory_exception=ApplicationInputError(
            f"logical_cycle_id must match [A-Za-z0-9_-]{{1,128}}; got {long_invalid_value!r}"
        )
    )
    with _client(fake) as client:
        response = client.post("/v1/advisory", json={"logical_cycle_id": long_invalid_value})
    assert response.status_code == 422
    assert long_invalid_value not in response.text
    # the response body itself stays small/fixed regardless of how large the
    # rejected input was - never proportional to caller-controlled content.
    assert len(response.text) < 300


# --- duplicate -----------------------------------------------------------


def test_duplicate_cycle_error_returns_409_with_identity_preserved() -> None:
    fake = FakeApplicationAdvisoryService(
        create_advisory_exception=DuplicateCycleError(logical_cycle_id="cycle-1", colliding_trade_ids=("cycle-1__TREND_FOLLOWING",))
    )
    with _client(fake) as client:
        response = client.post("/v1/advisory", json={"logical_cycle_id": "cycle-1"})
    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "DUPLICATE_CYCLE"
    assert body["error"]["logical_cycle_id"] == "cycle-1"
    assert body["error"]["colliding_trade_ids"] == ["cycle-1__TREND_FOLLOWING"]
    assert len(fake.create_advisory_calls) == 1  # no HTTP-layer retry


def test_duplicate_cycle_error_identity_strings_are_bounded_and_filesystem_safe() -> None:
    """Confirms the premise the handler's own docstring relies on: a
    colliding_trade_id can only ever be
    f"{logical_cycle_id}__{family.value}" for a logical_cycle_id that
    already passed [A-Za-z0-9_-]{1,128} - bounded, no path separator, no
    colon, no traversal token - safe to expose verbatim over HTTP."""
    long_valid_id = "a" * 128
    colliding = tuple(f"{long_valid_id}__{family}" for family in ("TREND_FOLLOWING", "MEAN_REVERSION", "BREAKOUT", "EVENT_DRIVEN"))
    fake = FakeApplicationAdvisoryService(create_advisory_exception=DuplicateCycleError(logical_cycle_id=long_valid_id, colliding_trade_ids=colliding))
    with _client(fake) as client:
        response = client.post("/v1/advisory", json={"logical_cycle_id": long_valid_id})
    assert response.status_code == 409
    body = response.json()
    for trade_id in body["error"]["colliding_trade_ids"]:
        assert len(trade_id) <= 145
        assert ":" not in trade_id
        assert "/" not in trade_id
        assert "\\" not in trade_id
        assert ".." not in trade_id


# --- state / internal ------------------------------------------------------


def test_application_state_error_returns_503_fixed_message_not_internal_text() -> None:
    fake = FakeApplicationAdvisoryService(create_advisory_exception=ApplicationStateError("run_cycle() requires a started composer (current state: NEW)"))
    with _client(fake) as client:
        response = client.post("/v1/advisory", json={"logical_cycle_id": "cycle-1"})
    assert response.status_code == 503
    body = response.json()
    assert body == {"error": {"code": "APPLICATION_STATE_ERROR", "message": "Application service is unavailable.", "logical_cycle_id": None, "colliding_trade_ids": []}}
    assert "requires a started composer" not in response.text
    assert "NEW" not in response.text


def test_internal_application_error_returns_500_generic_message_only() -> None:
    fake = FakeApplicationAdvisoryService(create_advisory_exception=InternalApplicationError("advisory cycle failed unexpectedly"))
    with _client(fake) as client:
        response = client.post("/v1/advisory", json={"logical_cycle_id": "cycle-1"})
    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert body["error"]["message"] == "An internal application error occurred."
    assert "advisory cycle failed unexpectedly" not in response.text


def test_generic_exception_never_leaks_secret_in_response_body() -> None:
    """An un-typed exception escaping the fake service (simulating something
    bypassing the real Application layer's own catch-all) is intentionally
    exercised here - Starlette's ``ServerErrorMiddleware`` always re-raises
    after invoking the registered handler (see its own source: "We always
    continue to raise the exception... allows test clients to optionally
    raise the error within the test case"), so this specific test needs
    ``raise_server_exceptions=False`` to inspect the produced response
    instead of failing on the propagated exception - every other test in
    this module (which only exercises typed ``ApplicationAdvisoryError``
    subclasses, all handled without any bare ``except Exception`` in
    ``app.application.advisory_service`` reaching this test's fake service)
    correctly uses the default ``TestClient``."""
    secret = "sk-FAKE-SECRET-VALUE-abcdef123456"
    fake = FakeApplicationAdvisoryService(create_advisory_exception=RuntimeError(f"connection failed, api_key={secret}"))
    with TestClient(create_app(service=fake), raise_server_exceptions=False) as client:
        response = client.post("/v1/advisory", json={"logical_cycle_id": "cycle-1"})
    assert response.status_code == 500
    assert secret not in response.text
    body = response.json()
    assert body == {"error": {"code": "INTERNAL_ERROR", "message": "An internal application error occurred.", "logical_cycle_id": None, "colliding_trade_ids": []}}


# --- SERVICE_UNAVAILABLE (structured) vs ApplicationStateError (ErrorResponse) ---


def test_structured_service_unavailable_and_state_error_503_are_not_conflated() -> None:
    """Both map to HTTP 503, but with genuinely distinct JSON shapes - the
    structured AdvisoryResponse body (a normal, non-error advisory result)
    must never be confusable with the ErrorResponse envelope."""
    from app.application.dto import ApplicationAdvisoryStatus

    structured_fake = FakeApplicationAdvisoryService(result=build_advisory_response(status=ApplicationAdvisoryStatus.SERVICE_UNAVAILABLE))
    with _client(structured_fake) as client:
        structured_response = client.post("/v1/advisory", json={"logical_cycle_id": "cycle-1"})

    state_error_fake = FakeApplicationAdvisoryService(create_advisory_exception=ApplicationStateError("not started"))
    with _client(state_error_fake) as client:
        state_error_response = client.post("/v1/advisory", json={"logical_cycle_id": "cycle-1"})

    assert structured_response.status_code == 503
    assert state_error_response.status_code == 503

    structured_body = structured_response.json()
    error_body = state_error_response.json()

    assert "error" not in structured_body
    assert "status" in structured_body
    assert "error" in error_body
    assert "status" not in error_body
