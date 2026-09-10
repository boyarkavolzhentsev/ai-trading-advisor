"""Lifespan tests: exactly one ``startup``/``shutdown`` per process, the
same injected service instance reused across every request, no per-request
construction."""

from __future__ import annotations

import importlib
import sys

import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.bootstrap.production import BootstrapConfigurationError
from tests.api_support import FakeApplicationAdvisoryService, build_advisory_response

_REQUIRED_PRODUCTION_ENV_VARS = (
    "ADVISORY_SYMBOL",
    "ADVISORY_CONTRACT_TYPE",
    "ADVISORY_MARKET",
    "MT5_ROLLOVER_TIMEZONE",
    "CALENDAR_BRIDGE_PATH",
    "CALENDAR_SERVER_TIMEZONE",
    "MT5_LOGIN",
    "MT5_PASSWORD",
    "MT5_SERVER",
    "OPENAI_API_KEY",
    "OPENAI_MODEL",
    "LLM_ENABLED",
)


def test_import_app_api_main_never_requires_production_env(monkeypatch) -> None:
    """Proves module-level ``app = create_app()`` is lazy: with every
    required production environment variable absent, plain
    ``import app.api.main`` must succeed and must never construct a
    ``ProductionAdvisoryComposer`` (which would fail loudly without those
    variables) - production construction only happens inside ``lifespan``,
    never at import time."""
    for name in _REQUIRED_PRODUCTION_ENV_VARS:
        monkeypatch.delenv(name, raising=False)

    sys.modules.pop("app.api.main", None)
    module = importlib.import_module("app.api.main")
    assert module.app is not None
    # the production lifespan is never entered by a plain import - no
    # TestClient/lifespan trigger happens in this test.


def test_startup_called_exactly_once() -> None:
    fake = FakeApplicationAdvisoryService(result=build_advisory_response())
    app = create_app(service=fake)
    with TestClient(app):
        pass
    assert fake.startup_calls == 1


def test_shutdown_called_exactly_once() -> None:
    fake = FakeApplicationAdvisoryService(result=build_advisory_response())
    app = create_app(service=fake)
    with TestClient(app):
        pass
    assert fake.shutdown_calls == 1


def test_same_service_instance_reused_across_requests() -> None:
    fake = FakeApplicationAdvisoryService(result=build_advisory_response())
    app = create_app(service=fake)
    with TestClient(app) as client:
        client.get("/health")
        client.post("/v1/advisory", json={"logical_cycle_id": "cycle-1"})
        client.post("/v1/advisory", json={"logical_cycle_id": "cycle-2"})
        stored = app.state.advisory_service
    assert stored is fake
    assert fake.create_advisory_calls == ["cycle-1", "cycle-2"]
    # exactly one startup/shutdown for the whole client lifetime, regardless
    # of how many requests were made through it.
    assert fake.startup_calls == 1
    assert fake.shutdown_calls == 1


def test_shutdown_not_yet_called_while_client_context_is_open() -> None:
    fake = FakeApplicationAdvisoryService(result=build_advisory_response())
    app = create_app(service=fake)
    with TestClient(app) as client:
        client.get("/health")
        assert fake.startup_calls == 1
        assert fake.shutdown_calls == 0
    assert fake.shutdown_calls == 1


# --- startup failure semantics (pre-commit security/lifespan review) -------


def test_production_config_failure_fails_server_startup_not_a_route(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing required production env vars must fail ASGI lifespan startup
    itself (TestClient context entry raises) - never degrade into a served
    /health=200 or an HTTP ErrorResponse. The server never became ready, so
    there is no route to serve at all."""
    for name in _REQUIRED_PRODUCTION_ENV_VARS:
        monkeypatch.delenv(name, raising=False)

    app = create_app()  # service=None -> production path, build_production_advisory_service() will raise
    with pytest.raises(BootstrapConfigurationError):
        with TestClient(app) as client:
            client.get("/health")  # never reached - context entry itself raises


def test_injected_service_startup_failure_fails_before_any_route_is_available() -> None:
    """A service whose own startup() raises must fail TestClient context
    entry - no request (not even /health) may succeed against a process
    that never finished starting up, and shutdown() must never be called on
    a service that never successfully started."""

    class FailingStartupService:
        def __init__(self) -> None:
            self.shutdown_calls = 0

        async def startup(self) -> None:
            raise RuntimeError("startup boom")

        async def shutdown(self) -> None:
            self.shutdown_calls += 1

        async def create_advisory(self, *, logical_cycle_id: str):
            raise NotImplementedError

    fake = FailingStartupService()
    app = create_app(service=fake)
    with pytest.raises(RuntimeError, match="startup boom"):
        with TestClient(app) as client:
            client.get("/health")
    # startup failed before yield - the try/finally guarding shutdown() was
    # never entered, so shutdown must never be called on a service that
    # never successfully started.
    assert fake.shutdown_calls == 0
