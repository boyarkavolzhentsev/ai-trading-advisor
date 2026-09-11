"""``ProductionAdvisoryComposer`` tests (Stage 0D Production Advisory
Composition): trade-ID coverage/ownership, wall-clock ownership, Technical
freshness safety policy, Flow health separation, calendar wiring, resource
ownership/lifecycle, and the LLM disabled fallback seam.

Duplicate/idempotency-preflight behavior lives in
``test_production_advisory_idempotency.py``.
"""

from __future__ import annotations

import ast
import inspect

import pytest

import app.production_advisory.composer as composer_module
from app.core.enums.explanation import ExplanationProviderStatus
from app.core.enums.strategy_router import StrategyFamily
from app.market_data.providers.binance.client import BinanceRestClient
from app.production_advisory.composer import ProductionAdvisoryComposer
from app.production_advisory.result import ProductionAdvisoryCycleOutcome
from tests.production_advisory_support import (
    AS_OF,
    FakeFlowBootstrap,
    FakeMT5Client,
    FakeRecordPersistence,
    all_trade_ids,
    build_config,
)


def _make_composer(**overrides: object) -> ProductionAdvisoryComposer:
    fields: dict[str, object] = {
        "config": build_config(),
        "flow_bootstrap": FakeFlowBootstrap(),
        "mt5_client": FakeMT5Client(),
        "tracking_persistence": FakeRecordPersistence(),
        "provenance_persistence": FakeRecordPersistence(),
    }
    fields.update(overrides)
    return ProductionAdvisoryComposer(**fields)  # type: ignore[arg-type]


def _fake_run_runtime_cycle(monkeypatch: pytest.MonkeyPatch):
    calls: list[dict[str, object]] = []

    def fake(**kwargs: object):
        calls.append(kwargs)
        from datetime import UTC, datetime

        from app.core.enums.runtime_cycle import RuntimeCycleOutcome
        from app.core.enums.mt5_runtime import MT5ConnectivityState
        from app.core.models.mt5_runtime import MT5RuntimeStatus
        from app.core.models.runtime_cycle import RuntimeCycleResult

        return RuntimeCycleResult(
            as_of=kwargs["as_of"],
            outcome=RuntimeCycleOutcome.BLOCKED,
            mt5_runtime_status=MT5RuntimeStatus(as_of=datetime.now(UTC), state=MT5ConnectivityState.TERMINAL_UNAVAILABLE),
        )

    monkeypatch.setattr(composer_module, "run_runtime_cycle", fake)
    return calls


# --- trade IDs -------------------------------------------------------------


@pytest.mark.asyncio
async def test_every_strategy_family_required(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_run_runtime_cycle(monkeypatch)
    composer = _make_composer()
    incomplete = {StrategyFamily.TREND_FOLLOWING: "T1"}
    with pytest.raises(ValueError, match="trade_ids missing entries"):
        await composer.startup()
        await composer.run_cycle(as_of=AS_OF, trade_ids=incomplete)


@pytest.mark.asyncio
async def test_complete_mapping_proceeds(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _fake_run_runtime_cycle(monkeypatch)
    composer = _make_composer()
    trade_ids = all_trade_ids()
    await composer.startup()
    result = await composer.run_cycle(as_of=AS_OF, trade_ids=trade_ids)
    assert result.outcome is ProductionAdvisoryCycleOutcome.SERVICE_UNAVAILABLE
    assert len(calls) == 1
    assert calls[0]["trade_ids"] == trade_ids


def test_composer_module_never_generates_ids() -> None:
    """AST-based (not substring) so this cannot false-positive on an
    explanatory docstring/comment mentioning these names in prose."""
    tree = ast.parse(inspect.getsource(composer_module))
    forbidden_names = {"uuid4", "uuid", "random", "secrets"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not any(alias.name in forbidden_names for alias in node.names)
        if isinstance(node, ast.ImportFrom) and node.module:
            assert node.module not in forbidden_names
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in forbidden_names
        if isinstance(node, ast.Attribute):
            assert node.attr not in {"uuid4"}


# --- wall-clock ownership ---------------------------------------------------


def test_composer_module_never_reads_wall_clock_for_business_logic() -> None:
    """Mirrors ``tests/test_mt5_rollover_calculation.py``'s own AST-based
    wall-clock check - ``time.perf_counter`` (operational diagnostics only)
    is deliberately NOT in this forbidden set."""
    tree = ast.parse(inspect.getsource(composer_module))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in {"now", "utcnow"}, "Stage0D composer must not read the wall clock"


@pytest.mark.asyncio
async def test_same_as_of_reaches_flow_technical_calendar_and_runtime(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    calls = _fake_run_runtime_cycle(monkeypatch)
    flow = FakeFlowBootstrap()
    composer = _make_composer(flow_bootstrap=flow, config=build_config(calendar_bridge_path=tmp_path / "absent.json"))
    await composer.startup()
    await composer.run_cycle(as_of=AS_OF, trade_ids=all_trade_ids())

    assert flow.build_calls == [AS_OF]
    assert calls[0]["as_of"] == AS_OF
    # calendar: an absent path still returns a typed context computed
    # against this same as_of (assert via the runtime call's own kwarg)
    assert calls[0]["high_impact_event_context"] is not None


@pytest.mark.asyncio
async def test_perf_counter_used_only_for_diagnostics_never_domain_logic(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_run_runtime_cycle(monkeypatch)
    composer = _make_composer()
    await composer.startup()
    result = await composer.run_cycle(as_of=AS_OF, trade_ids=all_trade_ids())
    assert result.cycle_duration_seconds >= 0.0
    assert result.outcome is ProductionAdvisoryCycleOutcome.SERVICE_UNAVAILABLE  # unaffected by timing


# --- Technical freshness safety policy -------------------------------------


@pytest.mark.asyncio
async def test_empty_fetch_failures_passes_technical_and_m15_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.production_advisory_support import FakeTechnicalComposer

    calls = _fake_run_runtime_cycle(monkeypatch)
    technical_composer = FakeTechnicalComposer(fetch_failures=())
    composer = _make_composer(technical_composer=technical_composer)
    await composer.startup()
    await composer.run_cycle(as_of=AS_OF, trade_ids=all_trade_ids())

    assert calls[0]["technical"] is technical_composer.sentinel_technical
    assert calls[0]["m15_market_structure"] is technical_composer.sentinel_m15


@pytest.mark.asyncio
async def test_any_fetch_failure_passes_technical_none(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.enums.market import Timeframe
    from app.technical.production import TechnicalFetchFailure
    from tests.production_advisory_support import FakeTechnicalComposer

    calls = _fake_run_runtime_cycle(monkeypatch)
    failure = TechnicalFetchFailure(timeframe=Timeframe.H4, error_type="ProviderUnavailableError")
    technical_composer = FakeTechnicalComposer(fetch_failures=(failure,))
    composer = _make_composer(technical_composer=technical_composer)
    await composer.startup()
    await composer.run_cycle(as_of=AS_OF, trade_ids=all_trade_ids())

    assert calls[0]["technical"] is None


@pytest.mark.asyncio
async def test_any_fetch_failure_passes_m15_market_structure_none(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.enums.market import Timeframe
    from app.technical.production import TechnicalFetchFailure
    from tests.production_advisory_support import FakeTechnicalComposer

    calls = _fake_run_runtime_cycle(monkeypatch)
    failure = TechnicalFetchFailure(timeframe=Timeframe.M15, error_type="ProviderUnavailableError")
    technical_composer = FakeTechnicalComposer(fetch_failures=(failure,))
    composer = _make_composer(technical_composer=technical_composer)
    await composer.startup()
    await composer.run_cycle(as_of=AS_OF, trade_ids=all_trade_ids())

    assert calls[0]["m15_market_structure"] is None


@pytest.mark.asyncio
async def test_old_valid_retained_technical_fake_cannot_bypass_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    """Even a technical/m15 payload that looks fully VALID (a stand-in for
    old-but-retained Stage 3A history) must still be discarded whenever
    ``fetch_failures`` is non-empty - the policy keys only on
    ``fetch_failures``, never on the payload's own apparent quality."""
    from app.core.enums.market import Timeframe
    from app.technical.production import TechnicalFetchFailure
    from tests.production_advisory_support import FakeTechnicalComposer

    calls = _fake_run_runtime_cycle(monkeypatch)
    failure = TechnicalFetchFailure(timeframe=Timeframe.H1, error_type="ProviderUnavailableError")
    technical_composer = FakeTechnicalComposer(fetch_failures=(failure,))
    # sentinel_technical/sentinel_m15 stand in for a fully "VALID"-looking
    # retained result - the policy must discard it anyway.
    composer = _make_composer(technical_composer=technical_composer)
    await composer.startup()
    await composer.run_cycle(as_of=AS_OF, trade_ids=all_trade_ids())

    assert calls[0]["technical"] is None
    assert calls[0]["m15_market_structure"] is None


# --- binance_reference_price discard safety (corrective design closure,
# "PROVIDER SYMBOL SPLIT + PRICE-BASIS RECONCILIATION") ----------------------


@pytest.mark.asyncio
async def test_empty_fetch_failures_passes_binance_reference_price_through(monkeypatch: pytest.MonkeyPatch) -> None:
    from decimal import Decimal

    from tests.production_advisory_support import FakeTechnicalComposer

    calls = _fake_run_runtime_cycle(monkeypatch)
    technical_composer = FakeTechnicalComposer(fetch_failures=(), m15_last_closed_close=Decimal("12345.6"))
    composer = _make_composer(technical_composer=technical_composer)
    await composer.startup()
    await composer.run_cycle(as_of=AS_OF, trade_ids=all_trade_ids())

    assert calls[0]["binance_reference_price"] == Decimal("12345.6")


@pytest.mark.asyncio
async def test_any_fetch_failure_forces_binance_reference_price_none_even_with_retained_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The exact mandatory regression this corrective design closure calls
    for: a retained old M15 close must never survive independently into
    Setup Construction once the current cycle's own Technical contour has
    been safety-discarded - even though ``m15_last_closed_close`` here is a
    real, present, non-None Decimal (standing in for genuinely retained
    Stage 3A history), ``fetch_failures`` being non-empty must still force
    ``binance_reference_price=None`` alongside ``technical``/
    ``m15_market_structure``. This prevents a hidden stale-reference-price
    seam."""
    from decimal import Decimal

    from app.core.enums.market import Timeframe
    from app.technical.production import TechnicalFetchFailure
    from tests.production_advisory_support import FakeTechnicalComposer

    calls = _fake_run_runtime_cycle(monkeypatch)
    failure = TechnicalFetchFailure(timeframe=Timeframe.M15, error_type="ProviderUnavailableError")
    technical_composer = FakeTechnicalComposer(fetch_failures=(failure,), m15_last_closed_close=Decimal("12345.6"))
    composer = _make_composer(technical_composer=technical_composer)
    await composer.startup()
    await composer.run_cycle(as_of=AS_OF, trade_ids=all_trade_ids())

    assert calls[0]["binance_reference_price"] is None
    assert calls[0]["technical"] is None
    assert calls[0]["m15_market_structure"] is None


# --- symbol_mapping / mt5_symbol routing to run_runtime_cycle ---------------


@pytest.mark.asyncio
async def test_mt5_symbol_and_binance_symbol_route_independently(monkeypatch: pytest.MonkeyPatch) -> None:
    """Corrective design closure ("PROVIDER SYMBOL SPLIT + PRICE-BASIS
    RECONCILIATION"): run_runtime_cycle receives the MT5 broker symbol as
    its own explicit ``mt5_symbol`` argument, distinct from the Binance
    symbol embedded in ``context`` (Flow/Technical/Market Evaluation's own
    analytical identity) - never the same field doing double duty."""
    from app.production_advisory.config import SymbolMapping
    from tests.production_advisory_support import build_config

    calls = _fake_run_runtime_cycle(monkeypatch)
    mapping = SymbolMapping(logical_symbol="BTC", binance_symbol="BTCUSDT", mt5_symbol="BTCUSDt")
    composer = _make_composer(config=build_config(symbol_mapping=mapping))
    await composer.startup()
    await composer.run_cycle(as_of=AS_OF, trade_ids=all_trade_ids())

    assert calls[0]["mt5_symbol"] == "BTCUSDt"
    assert calls[0]["context"].symbol == "BTCUSDT"


@pytest.mark.asyncio
async def test_max_price_basis_divergence_percent_passed_through(monkeypatch: pytest.MonkeyPatch) -> None:
    from decimal import Decimal

    from tests.production_advisory_support import build_config

    calls = _fake_run_runtime_cycle(monkeypatch)
    composer = _make_composer(config=build_config(max_price_basis_divergence_percent=Decimal("7.5")))
    await composer.startup()
    await composer.run_cycle(as_of=AS_OF, trade_ids=all_trade_ids())

    assert calls[0]["max_price_basis_divergence_percent"] == Decimal("7.5")


def test_default_flow_bootstrap_uses_binance_symbol_never_mt5_symbol() -> None:
    """Pure object-graph construction only - no network, no real connection.
    ``_default_flow_bootstrap`` must build its FlowRealtimeBootstrapConfig
    from symbol_mapping.binance_symbol, never symbol_mapping.mt5_symbol."""
    from app.market_data.providers.binance.client import BinanceRestClient
    from app.production_advisory.config import SymbolMapping
    from tests.production_advisory_support import build_config

    mapping = SymbolMapping(logical_symbol="BTC", binance_symbol="BTCUSDT", mt5_symbol="BTCUSDt")
    config = build_config(symbol_mapping=mapping)
    rest_client = BinanceRestClient()
    try:
        bootstrap = composer_module._default_flow_bootstrap(config, rest_client)
        assert bootstrap._config.symbol == "BTCUSDT"
        assert bootstrap._config.symbol != "BTCUSDt"
    finally:
        rest_client.close()


def test_default_technical_composer_uses_binance_symbol_never_mt5_symbol() -> None:
    from app.market_data.providers.binance.client import BinanceRestClient
    from app.production_advisory.config import SymbolMapping
    from tests.production_advisory_support import build_config

    mapping = SymbolMapping(logical_symbol="BTC", binance_symbol="BTCUSDT", mt5_symbol="BTCUSDt")
    config = build_config(symbol_mapping=mapping)
    rest_client = BinanceRestClient()
    try:
        technical_composer = composer_module._default_technical_composer(config, rest_client)
        assert technical_composer._config.symbol == "BTCUSDT"
        assert technical_composer._config.symbol != "BTCUSDt"
    finally:
        rest_client.close()


# --- Flow health vs. trading evidence ---------------------------------------


@pytest.mark.asyncio
async def test_flow_health_never_passed_as_trading_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _fake_run_runtime_cycle(monkeypatch)
    composer = _make_composer()
    await composer.startup()
    result = await composer.run_cycle(as_of=AS_OF, trade_ids=all_trade_ids())

    call_kwargs = calls[0]
    assert result.flow_health not in call_kwargs.values()
    assert "flow_health" not in call_kwargs
    assert call_kwargs["flow"] is None  # FakeFlowBootstrap.build_flow_result's own return, not health()


# --- resource ownership / lifecycle ----------------------------------------


@pytest.mark.asyncio
async def test_startup_starts_flow_exactly_once() -> None:
    flow = FakeFlowBootstrap()
    composer = _make_composer(flow_bootstrap=flow)
    await composer.startup()
    assert flow.start_calls == 1


@pytest.mark.asyncio
async def test_shutdown_stops_flow_exactly_once() -> None:
    flow = FakeFlowBootstrap()
    composer = _make_composer(flow_bootstrap=flow)
    await composer.shutdown()
    assert flow.stop_calls == 1


@pytest.mark.asyncio
async def test_shutdown_never_closes_a_caller_injected_rest_client() -> None:
    closed = []
    fake_rest_client = type("FakeRestClient", (), {"close": lambda self: closed.append(1)})()
    composer = _make_composer(rest_client=fake_rest_client)
    await composer.shutdown()
    assert closed == []


@pytest.mark.asyncio
async def test_shutdown_closes_owned_rest_client_exactly_once() -> None:
    composer = _make_composer()  # rest_client not injected -> composer owns it
    close_calls = []
    composer._rest_client.close = lambda: close_calls.append(1)  # type: ignore[method-assign]
    await composer.shutdown()
    assert close_calls == [1]


def test_flow_and_technical_share_exactly_one_binance_rest_client() -> None:
    """When neither Flow nor Technical composer is injected, the real
    defaults must be built from the SAME shared client - never two
    separate ones."""
    composer = ProductionAdvisoryComposer(config=build_config(), mt5_client=FakeMT5Client())
    assert isinstance(composer._rest_client, BinanceRestClient)
    assert composer._flow_bootstrap._rest_client is composer._rest_client  # type: ignore[attr-defined]
    assert composer._technical_composer._provider._client is composer._rest_client  # type: ignore[attr-defined]
    composer._rest_client.close()


@pytest.mark.asyncio
async def test_stage0d_never_calls_mt5_directly(monkeypatch: pytest.MonkeyPatch) -> None:
    """``FakeMT5Client`` raises ``AssertionError`` from every method other
    than ``initialize``/``shutdown`` - proving Stage0D itself never calls
    them (only the monkeypatched ``run_runtime_cycle`` stand-in is exercised
    here, so a real call would have to come from the composer directly)."""
    _fake_run_runtime_cycle(monkeypatch)
    composer = _make_composer()
    await composer.startup()
    await composer.run_cycle(as_of=AS_OF, trade_ids=all_trade_ids())  # would raise if composer touched MT5 itself


# --- calendar ----------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_calendar_file_still_reaches_runtime_with_unavailable_context(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    from app.core.enums.high_impact_event import HighImpactEventDataQuality

    calls = _fake_run_runtime_cycle(monkeypatch)
    config = build_config(calendar_bridge_path=tmp_path / "absent.json")
    composer = _make_composer(config=config)
    await composer.startup()
    await composer.run_cycle(as_of=AS_OF, trade_ids=all_trade_ids())

    context = calls[0]["high_impact_event_context"]
    assert context.data_quality is HighImpactEventDataQuality.UNAVAILABLE


@pytest.mark.asyncio
async def test_calendar_timezone_config_passed_through(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    import json

    from app.core.config.high_impact_event_bridge import HighImpactEventCalendarTimezoneConfig

    calls = _fake_run_runtime_cycle(monkeypatch)
    path = tmp_path / "calendar.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "producer": "mt5_calendar_bridge",
                "generated_at": AS_OF.isoformat().replace("+00:00", "Z"),
                "events": [],
            }
        ),
        encoding="utf-8",
    )
    tz = HighImpactEventCalendarTimezoneConfig(server_timezone="Europe/Nicosia")
    config = build_config(calendar_bridge_path=path, calendar_server_timezone=tz)
    composer = _make_composer(config=config)
    await composer.startup()
    await composer.run_cycle(as_of=AS_OF, trade_ids=all_trade_ids())

    context = calls[0]["high_impact_event_context"]
    assert context.data_quality.value == "FRESH"


@pytest.mark.asyncio
async def test_fifteen_minute_default_threshold_used(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    import json
    from datetime import timedelta

    calls = _fake_run_runtime_cycle(monkeypatch)
    path = tmp_path / "calendar.json"
    stale_generated_at = (AS_OF - timedelta(minutes=20)).isoformat().replace("+00:00", "Z")
    path.write_text(
        json.dumps({"schema_version": 2, "producer": "mt5_calendar_bridge", "generated_at": stale_generated_at, "events": []}),
        encoding="utf-8",
    )
    config = build_config(calendar_bridge_path=path)
    composer = _make_composer(config=config)
    await composer.startup()
    await composer.run_cycle(as_of=AS_OF, trade_ids=all_trade_ids())

    context = calls[0]["high_impact_event_context"]
    assert context.data_quality.value == "STALE"  # 20 minutes old > the 15-minute default


# --- LLM ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_explanation_called_after_runtime_with_result_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _fake_run_runtime_cycle(monkeypatch)
    composer = _make_composer()
    await composer.startup()
    result = await composer.run_cycle(as_of=AS_OF, trade_ids=all_trade_ids())
    assert result.runtime_cycle_result.outcome.value == "BLOCKED"
    assert result.explanation_result is not None


@pytest.mark.asyncio
async def test_llm_disabled_uses_deterministic_fallback_with_no_extra_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_run_runtime_cycle(monkeypatch)
    composer = _make_composer(config=build_config())  # llm_enabled=False by default
    await composer.startup()
    result = await composer.run_cycle(as_of=AS_OF, trade_ids=all_trade_ids())
    assert result.explanation_result.provider_status is ExplanationProviderStatus.LLM_UNAVAILABLE
    assert result.explanation_result.content_status.value == "AVAILABLE"  # deterministic fallback still usable
    assert result.llm_enabled is False  # disabled, not "provider failed" - the disambiguating fact


@pytest.mark.asyncio
async def test_provider_failure_uses_existing_deterministic_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.production_advisory_support import RaisingExplanationClient

    _fake_run_runtime_cycle(monkeypatch)
    composer = _make_composer(llm_client=RaisingExplanationClient())
    await composer.startup()
    result = await composer.run_cycle(as_of=AS_OF, trade_ids=all_trade_ids())
    assert result.explanation_result.provider_status is ExplanationProviderStatus.LLM_UNAVAILABLE
    assert result.llm_enabled is True  # enabled but the provider itself failed - distinct from disabled


def test_llm_enabled_distinguishable_from_provider_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """The exact invariant the LLM-disabled-semantics review required:
    both cases report the identical ``provider_status`` (no DISABLED
    member exists on ``ExplanationProviderStatus``), but Stage0D's own
    ``llm_enabled`` field disambiguates them for a future status
    consumer - never conflated."""
    from tests.production_advisory_support import RaisingExplanationClient

    disabled = ProductionAdvisoryComposer(
        config=build_config(),
        flow_bootstrap=FakeFlowBootstrap(),
        mt5_client=FakeMT5Client(),
        tracking_persistence=FakeRecordPersistence(),
        provenance_persistence=FakeRecordPersistence(),
    )
    enabled_but_failing = ProductionAdvisoryComposer(
        config=build_config(),
        flow_bootstrap=FakeFlowBootstrap(),
        mt5_client=FakeMT5Client(),
        tracking_persistence=FakeRecordPersistence(),
        provenance_persistence=FakeRecordPersistence(),
        llm_client=RaisingExplanationClient(),
    )
    assert disabled._llm_enabled is False
    assert enabled_but_failing._llm_enabled is True


# --- outcome classification -------------------------------------------------


def _fake_run_runtime_cycle_with_outcome(monkeypatch: pytest.MonkeyPatch, outcome: str):
    from app.core.enums.mt5_runtime import MT5ConnectivityState
    from app.core.enums.runtime_cycle import RuntimeCycleOutcome
    from app.core.models.mt5_runtime import MT5RuntimeStatus
    from app.core.models.runtime_cycle import RuntimeCycleResult
    from datetime import UTC, datetime

    state = MT5ConnectivityState.TERMINAL_UNAVAILABLE if outcome == "BLOCKED" else MT5ConnectivityState.AVAILABLE

    def fake(**kwargs: object):
        return RuntimeCycleResult(
            as_of=kwargs["as_of"],
            outcome=RuntimeCycleOutcome(outcome),
            mt5_runtime_status=MT5RuntimeStatus(as_of=datetime.now(UTC), state=state),
        )

    monkeypatch.setattr(composer_module, "run_runtime_cycle", fake)


@pytest.mark.asyncio
async def test_genuine_mt5_unavailable_condition_is_service_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """RuntimeCycleOutcome.BLOCKED's own docstring, and its single
    call site in app/orchestration/runtime_cycle.py (the MT5-connectivity
    check at the very top of run_runtime_cycle), prove it means exactly
    "MT5 connectivity itself was unavailable this cycle" - the only
    condition that should ever map to SERVICE_UNAVAILABLE."""
    _fake_run_runtime_cycle_with_outcome(monkeypatch, "BLOCKED")
    composer = _make_composer()
    await composer.startup()
    result = await composer.run_cycle(as_of=AS_OF, trade_ids=all_trade_ids())
    assert result.outcome is ProductionAdvisoryCycleOutcome.SERVICE_UNAVAILABLE


@pytest.mark.asyncio
async def test_ready_domain_outcome_is_never_service_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_run_runtime_cycle_with_outcome(monkeypatch, "READY")
    composer = _make_composer()
    await composer.startup()
    result = await composer.run_cycle(as_of=AS_OF, trade_ids=all_trade_ids())
    assert result.outcome is ProductionAdvisoryCycleOutcome.READY


@pytest.mark.asyncio
async def test_partial_degraded_domain_block_is_never_service_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """PARTIAL_DEGRADED can legitimately represent a NETTING/UNKNOWN
    issuance guard block, a corrupt tracked recommendation, or a
    persistence write failure (see RuntimeCycleOutcome's own docstring) -
    none of these is an infrastructure/service-unavailability fact, and
    none may ever be labeled SERVICE_UNAVAILABLE."""
    _fake_run_runtime_cycle_with_outcome(monkeypatch, "PARTIAL_DEGRADED")
    composer = _make_composer()
    await composer.startup()
    result = await composer.run_cycle(as_of=AS_OF, trade_ids=all_trade_ids())
    assert result.outcome is ProductionAdvisoryCycleOutcome.READY
    assert result.outcome is not ProductionAdvisoryCycleOutcome.SERVICE_UNAVAILABLE


# --- lifecycle guards --------------------------------------------------------


@pytest.mark.asyncio
async def test_run_cycle_before_startup_raises_lifecycle_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.production_advisory.errors import ProductionAdvisoryLifecycleError

    _fake_run_runtime_cycle(monkeypatch)
    composer = _make_composer()
    with pytest.raises(ProductionAdvisoryLifecycleError, match="requires a started composer"):
        await composer.run_cycle(as_of=AS_OF, trade_ids=all_trade_ids())


@pytest.mark.asyncio
async def test_run_cycle_after_shutdown_raises_lifecycle_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.production_advisory.errors import ProductionAdvisoryLifecycleError

    _fake_run_runtime_cycle(monkeypatch)
    composer = _make_composer()
    await composer.startup()
    await composer.shutdown()
    with pytest.raises(ProductionAdvisoryLifecycleError, match="requires a started composer"):
        await composer.run_cycle(as_of=AS_OF, trade_ids=all_trade_ids())


@pytest.mark.asyncio
async def test_startup_called_twice_is_idempotent_flow_started_once() -> None:
    flow = FakeFlowBootstrap()
    composer = _make_composer(flow_bootstrap=flow)
    await composer.startup()
    await composer.startup()
    assert flow.start_calls == 1


@pytest.mark.asyncio
async def test_shutdown_called_twice_is_idempotent_flow_stopped_once() -> None:
    flow = FakeFlowBootstrap()
    composer = _make_composer(flow_bootstrap=flow)
    await composer.startup()
    await composer.shutdown()
    await composer.shutdown()
    assert flow.stop_calls == 1


@pytest.mark.asyncio
async def test_startup_after_shutdown_raises_lifecycle_error_deterministically() -> None:
    from app.production_advisory.errors import ProductionAdvisoryLifecycleError

    composer = _make_composer()
    await composer.startup()
    await composer.shutdown()
    with pytest.raises(ProductionAdvisoryLifecycleError, match="cannot be called after shutdown"):
        await composer.startup()


@pytest.mark.asyncio
async def test_shutdown_from_new_state_is_safe_and_idempotent() -> None:
    """shutdown() before startup() was ever called must never raise -
    only run_cycle()/startup()-after-shutdown are guarded failures."""
    flow = FakeFlowBootstrap()
    composer = _make_composer(flow_bootstrap=flow)
    await composer.shutdown()
    assert flow.stop_calls == 1  # FlowRealtimeBootstrap.stop() is itself a safe no-op when never started
