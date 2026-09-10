"""``ApplicationAdvisoryService`` tests: clock ownership, lifecycle
delegation, error mapping, and the SERVICE_UNAVAILABLE-as-structured-output
contract. The composer itself is a narrow fake - these tests never construct
a real ``ProductionAdvisoryComposer``/touch MT5/Binance/OpenAI."""

from __future__ import annotations

import ast
import inspect
from datetime import UTC, datetime

import pytest

import app.application.advisory_service as service_module
from app.application.advisory_service import ApplicationAdvisoryService
from app.application.errors import (
    ApplicationAdvisoryError,
    ApplicationInputError,
    ApplicationStateError,
    DuplicateCycleError,
    InternalApplicationError,
)
from app.core.enums.mt5_matching import MT5TrackedRecommendationCreationOutcome
from app.core.enums.runtime_cycle import NettingIssuanceOutcome, RuntimeCycleOutcome
from app.core.enums.strategy_router import StrategyFamily
from app.production_advisory.errors import ProductionAdvisoryDuplicateCycleError, ProductionAdvisoryLifecycleError
from app.production_advisory.result import ProductionAdvisoryCycleOutcome
from tests.application_support import (
    full_actionable_pipeline,
    netting_guard,
    production_advisory_cycle_result,
    runtime_cycle_result,
    tracking_outcome,
)


class FakeComposer:
    """Records every ``run_cycle``/``startup``/``shutdown`` call. Returns a
    caller-configured ``ProductionAdvisoryCycleResult`` or raises a
    caller-configured exception - never touches MT5/Binance/OpenAI/a real
    ``ProductionAdvisoryComposer``."""

    def __init__(self, *, result=None, run_cycle_exception: Exception | None = None, startup_exception: Exception | None = None) -> None:
        self._result = result
        self._run_cycle_exception = run_cycle_exception
        self._startup_exception = startup_exception
        self.startup_calls = 0
        self.shutdown_calls = 0
        self.run_cycle_calls: list[dict[str, object]] = []

    async def startup(self) -> None:
        self.startup_calls += 1
        if self._startup_exception is not None:
            raise self._startup_exception

    async def shutdown(self) -> None:
        self.shutdown_calls += 1

    async def run_cycle(self, *, as_of, trade_ids):
        self.run_cycle_calls.append({"as_of": as_of, "trade_ids": trade_ids})
        if self._run_cycle_exception is not None:
            raise self._run_cycle_exception
        assert self._result is not None
        return self._result


def _service_unavailable_cycle():
    rcr = runtime_cycle_result(outcome=RuntimeCycleOutcome.BLOCKED)
    return production_advisory_cycle_result(rcr=rcr, outcome=ProductionAdvisoryCycleOutcome.SERVICE_UNAVAILABLE)


def _ready_cycle_with_one_recommendation():
    family = StrategyFamily.TREND_FOLLOWING
    trade_ids = {f: f"TID__{f.value}" for f in StrategyFamily}
    drp, frcr = full_actionable_pipeline(trade_ids)
    tracking = tuple(
        tracking_outcome(tid, MT5TrackedRecommendationCreationOutcome.CREATED if fam is family else MT5TrackedRecommendationCreationOutcome.SNAPSHOT_UNAVAILABLE)
        for fam, tid in trade_ids.items()
    )
    rcr = runtime_cycle_result(
        outcome=RuntimeCycleOutcome.READY,
        decision_risk_pipeline_result=drp,
        final_recommendation_construction_result=frcr,
        netting_guard_result=netting_guard(NettingIssuanceOutcome.BLOCKED_MULTIPLE_ACTIONABLE_RECOMMENDATIONS),
        new_tracking_persistence_outcomes=tracking,
    )
    return production_advisory_cycle_result(rcr=rcr, outcome=ProductionAdvisoryCycleOutcome.READY)


# --- clock ownership ---------------------------------------------------


@pytest.mark.asyncio
async def test_exactly_one_wall_clock_capture_per_call(monkeypatch: pytest.MonkeyPatch) -> None:
    fixed_now = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
    calls = {"count": 0}

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            calls["count"] += 1
            return fixed_now

    monkeypatch.setattr(service_module, "datetime", FrozenDatetime)
    composer = FakeComposer(result=_service_unavailable_cycle())
    service = ApplicationAdvisoryService(composer=composer)
    await service.create_advisory(logical_cycle_id="cycle-1")

    assert calls["count"] == 1
    assert composer.run_cycle_calls[0]["as_of"] == fixed_now


@pytest.mark.asyncio
async def test_derived_trade_ids_passed_unchanged() -> None:
    from app.application.identity import derive_trade_ids

    composer = FakeComposer(result=_service_unavailable_cycle())
    service = ApplicationAdvisoryService(composer=composer)
    await service.create_advisory(logical_cycle_id="cycle-abc")

    assert composer.run_cycle_calls[0]["trade_ids"] == derive_trade_ids("cycle-abc")


@pytest.mark.asyncio
async def test_no_cache_no_second_run_cycle_invocation() -> None:
    composer = FakeComposer(result=_service_unavailable_cycle())
    service = ApplicationAdvisoryService(composer=composer)
    await service.create_advisory(logical_cycle_id="cycle-1")
    assert len(composer.run_cycle_calls) == 1
    # a second, distinct logical_cycle_id triggers a second, independent call -
    # never a cached/reused result.
    await service.create_advisory(logical_cycle_id="cycle-2")
    assert len(composer.run_cycle_calls) == 2


def test_advisory_service_never_reads_wall_clock_outside_create_advisory() -> None:
    """Mirrors ``tests/test_production_advisory_composer.py``'s own AST
    check - the only permitted ``datetime.now``/``utcnow`` call in this
    module is the single capture inside ``create_advisory``."""
    tree = ast.parse(inspect.getsource(service_module))
    now_calls = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in {"now", "utcnow"}:
            now_calls += 1
    assert now_calls == 1


# --- SERVICE_UNAVAILABLE: structured output, never an exception --------


@pytest.mark.asyncio
async def test_service_unavailable_returns_structured_response_not_exception() -> None:
    composer = FakeComposer(result=_service_unavailable_cycle())
    service = ApplicationAdvisoryService(composer=composer)
    response = await service.create_advisory(logical_cycle_id="cycle-1")

    from app.application.dto import ApplicationAdvisoryStatus

    assert response.status is ApplicationAdvisoryStatus.SERVICE_UNAVAILABLE
    assert response.recommendations == ()


def test_service_unavailable_error_class_does_not_exist() -> None:
    import app.application.errors as errors_module

    assert not hasattr(errors_module, "ServiceUnavailableError")


# --- error mapping -------------------------------------------------------


@pytest.mark.asyncio
async def test_duplicate_cycle_error_preserves_identity_and_colliding_ids() -> None:
    colliding = ("cycle-1__TREND_FOLLOWING",)
    composer = FakeComposer(run_cycle_exception=ProductionAdvisoryDuplicateCycleError(colliding))
    service = ApplicationAdvisoryService(composer=composer)

    with pytest.raises(DuplicateCycleError) as exc_info:
        await service.create_advisory(logical_cycle_id="cycle-1")

    assert exc_info.value.logical_cycle_id == "cycle-1"
    assert exc_info.value.colliding_trade_ids == colliding


@pytest.mark.asyncio
async def test_duplicate_retry_does_not_regenerate_identity() -> None:
    composer = FakeComposer(run_cycle_exception=ProductionAdvisoryDuplicateCycleError(("x",)))
    service = ApplicationAdvisoryService(composer=composer)
    with pytest.raises(DuplicateCycleError):
        await service.create_advisory(logical_cycle_id="cycle-1")
    with pytest.raises(DuplicateCycleError):
        await service.create_advisory(logical_cycle_id="cycle-1")
    # both attempts derived and sent the identical trade_ids mapping - no new identity.
    assert composer.run_cycle_calls[0]["trade_ids"] == composer.run_cycle_calls[1]["trade_ids"]


@pytest.mark.asyncio
async def test_lifecycle_error_from_run_cycle_maps_to_application_state_error() -> None:
    composer = FakeComposer(run_cycle_exception=ProductionAdvisoryLifecycleError("not started"))
    service = ApplicationAdvisoryService(composer=composer)
    with pytest.raises(ApplicationStateError):
        await service.create_advisory(logical_cycle_id="cycle-1")


@pytest.mark.asyncio
async def test_lifecycle_error_from_startup_maps_to_application_state_error() -> None:
    composer = FakeComposer(startup_exception=ProductionAdvisoryLifecycleError("cannot restart"))
    service = ApplicationAdvisoryService(composer=composer)
    with pytest.raises(ApplicationStateError):
        await service.startup()


@pytest.mark.asyncio
async def test_invalid_logical_cycle_id_raises_input_error_without_calling_run_cycle() -> None:
    composer = FakeComposer(result=_service_unavailable_cycle())
    service = ApplicationAdvisoryService(composer=composer)
    with pytest.raises(ApplicationInputError):
        await service.create_advisory(logical_cycle_id="has:colon")
    assert composer.run_cycle_calls == []


@pytest.mark.asyncio
async def test_stage0d_value_error_after_valid_identity_maps_to_internal_error() -> None:
    composer = FakeComposer(run_cycle_exception=ValueError("trade_ids missing entries for: ['BREAKOUT']"))
    service = ApplicationAdvisoryService(composer=composer)
    with pytest.raises(InternalApplicationError):
        await service.create_advisory(logical_cycle_id="cycle-1")


@pytest.mark.asyncio
async def test_unexpected_exception_does_not_leak_secret_in_outward_message() -> None:
    secret = "sk-FAKE-SECRET-VALUE-1234567890"
    composer = FakeComposer(run_cycle_exception=RuntimeError(f"connection failed, api_key={secret}"))
    service = ApplicationAdvisoryService(composer=composer)
    with pytest.raises(InternalApplicationError) as exc_info:
        await service.create_advisory(logical_cycle_id="cycle-1")

    assert secret not in str(exc_info.value)
    assert secret not in repr(exc_info.value)
    # the original exception remains available via chaining, for logging only
    assert secret in str(exc_info.value.__cause__)


@pytest.mark.asyncio
async def test_lifecycle_delegates_to_composer_exactly_once() -> None:
    composer = FakeComposer()
    service = ApplicationAdvisoryService(composer=composer)
    await service.startup()
    await service.shutdown()
    assert composer.startup_calls == 1
    assert composer.shutdown_calls == 1


# --- module hygiene -------------------------------------------------------


_FORBIDDEN_IMPORTS = {
    "MT5Client",
    "BinanceRestClient",
    "OpenAIExplanationClient",
    "Judge",
    "RiskGate",
    "PortfolioSupervisor",
    "SessionGate",
    "SetupConstruction",
    "run_runtime_cycle",
}


@pytest.mark.parametrize("module_name", ["app.application.advisory_service", "app.application.dto", "app.application.identity", "app.application.errors"])
def test_application_modules_never_import_closed_execution_seams(module_name: str) -> None:
    import importlib

    module = importlib.import_module(module_name)
    tree = ast.parse(inspect.getsource(module))
    imported_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported_names.update(alias.asname or alias.name for alias in node.names)
        if isinstance(node, ast.Import):
            imported_names.update(alias.asname or alias.name for alias in node.names)
    assert imported_names.isdisjoint(_FORBIDDEN_IMPORTS), imported_names & _FORBIDDEN_IMPORTS
