"""Shared fakes/builders for Stage 0D Production Advisory Composition tests.

Not a test module itself (no ``test_`` prefix): pytest will not collect it.
Every fake is a narrow, protocol-shaped stand-in - none imports a real SDK,
MT5, or the network.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from app.core.config.high_impact_event_bridge import HighImpactEventCalendarTimezoneConfig
from app.core.config.mt5_rollover import MT5RolloverPolicyConfig
from app.core.enums.instrument import ContractType
from app.core.enums.market import MarketType
from app.core.enums.mt5_runtime import MT5ConnectivityState
from app.core.enums.strategy_router import StrategyFamily
from app.core.models.mt5_runtime import MT5AccountFacts, MT5RuntimeStatus
from app.core.models.stream_health import StreamHealth
from app.flow.open_interest_poller import TaskHealth, TaskState
from app.flow.realtime_bootstrap import FlowRealtimeBootstrapHealth
from app.mt5.errors import MT5NotInitializedError
from app.production_advisory.config import ProductionAdvisoryConfig, SymbolMapping
from app.technical.production import TechnicalFetchFailure, TechnicalProductionResult

AS_OF = datetime(2026, 1, 2, 14, 30, 0, tzinfo=UTC)

ReadStatus = Literal["ABSENT", "VALID", "CORRUPT", "UNAVAILABLE"]


def all_trade_ids(prefix: str = "TID") -> dict[StrategyFamily, str]:
    """One deterministic trade_id per ``StrategyFamily`` - never random."""
    return {family: f"{prefix}-{family.value}" for family in StrategyFamily}


def build_config(**overrides: object) -> ProductionAdvisoryConfig:
    fields: dict[str, object] = {
        "symbol_mapping": SymbolMapping(logical_symbol="EURUSD", binance_symbol="EURUSD", mt5_symbol="EURUSD"),
        "contract_type": ContractType.PERPETUAL,
        "market": MarketType.FX,
        "rollover_policy": MT5RolloverPolicyConfig(rollover_timezone="UTC"),
        "rollover_state_path": Path("rollover_state.json"),
        "tracking_directory": Path("tracking"),
        "provenance_directory": Path("provenance"),
        "calendar_bridge_path": Path("calendar_bridge_absent.json"),
        "calendar_server_timezone": HighImpactEventCalendarTimezoneConfig(server_timezone="UTC"),
    }
    fields.update(overrides)
    return ProductionAdvisoryConfig(**fields)


class FakeFlowBootstrap:
    """Records start/stop calls and every ``as_of`` it was built with."""

    def __init__(self) -> None:
        self.start_calls = 0
        self.stop_calls = 0
        self.build_calls: list[object] = []

    async def start(self) -> None:
        self.start_calls += 1

    async def stop(self) -> None:
        self.stop_calls += 1

    def build_flow_result(self, *, as_of: object) -> None:
        self.build_calls.append(as_of)
        return None

    def health(self) -> FlowRealtimeBootstrapHealth:
        now = datetime.now(UTC)
        stream = StreamHealth(provider="fake", stream="market", status="CONNECTED", checked_at=now)
        task = TaskHealth(state=TaskState.RUNNING)
        return FlowRealtimeBootstrapHealth(
            market=stream,
            order_book=stream,
            open_interest_last_attempt_at=None,
            open_interest_last_success_at=None,
            market_transport_task=task,
            public_transport_task=task,
            trades_task=task,
            liquidations_task=task,
            order_book_task=task,
            funding_task=task,
            funding_cache_refresh_task=task,
            open_interest_task=task,
        )


class FakeTechnicalComposer:
    """Returns a caller-configured ``fetch_failures`` tuple; records every
    ``as_of`` it was called with."""

    def __init__(self, fetch_failures: tuple[TechnicalFetchFailure, ...] = ()) -> None:
        self.fetch_failures = fetch_failures
        self.build_calls: list[object] = []
        self.sentinel_technical = object()
        self.sentinel_m15 = object()

    def build_technical_result(self, *, as_of: object) -> TechnicalProductionResult:
        self.build_calls.append(as_of)
        return TechnicalProductionResult(
            technical=self.sentinel_technical,  # type: ignore[arg-type]
            m15_market_structure=self.sentinel_m15,  # type: ignore[arg-type]
            fetch_failures=self.fetch_failures,
        )


class FakeMT5Client:
    """Always reports connectivity unavailable - the smallest fake that
    lets a full cycle complete deterministically without touching real
    MT5. Never implements order/execution surfaces (there are none on
    ``MT5ClientProtocol`` to implement).

    ``rates()`` (MT5 Price Authority Stage B lifecycle correction: the
    default Technical composer wires ``MT5OHLCVProvider(client=mt5_client,
    ...)`` against this SAME fake) raises ``MT5NotInitializedError`` -
    exactly like the real ``app.mt5.client.MT5Client`` does - rather than
    returning ``"UNAVAILABLE"``: this fake's own ``initialize()`` always
    reports ``INITIALIZATION_FAILED`` (the raw connection itself never
    succeeds), which in the real client means every initialized-only method
    raises rather than gracefully degrading, and ``rates()`` must model that
    faithfully or a genuine "Technical read before MT5 initialize" defect
    would go undetected (see ``test_production_advisory_mt5_lifecycle.py``
    for the dedicated lifecycle-ordering fixture, ``LifecycleTrackingMT5Client``,
    used where a test needs a client that CAN reach ``AVAILABLE``)."""

    def initialize(self) -> MT5RuntimeStatus:
        return MT5RuntimeStatus(as_of=datetime.now(UTC), state=MT5ConnectivityState.INITIALIZATION_FAILED, reason="fake: no terminal")

    def runtime_status(self) -> MT5RuntimeStatus:
        raise AssertionError("runtime_status() must not be called directly by Stage0D")

    def account_facts(self) -> None:
        raise AssertionError("account_facts() must not be called directly by Stage0D")

    def positions(self) -> tuple[str, tuple]:
        raise AssertionError("positions() must not be called directly by Stage0D")

    def symbol_facts(self, symbol: str) -> None:
        raise AssertionError("symbol_facts() must not be called directly by Stage0D")

    def history_deals(self, *, start: object, end: object) -> tuple[str, tuple]:
        raise AssertionError("history_deals() must not be called directly by Stage0D")

    def rates(self, *, symbol: str, timeframe: object, count: int) -> tuple[str, tuple]:
        raise MT5NotInitializedError("rates() called before a successful initialize() (fake: initialize() always fails)")

    def shutdown(self) -> None:
        pass


class LifecycleTrackingMT5Client:
    """MT5 Price Authority Stage B lifecycle-correction fixture: implements
    ``MT5ClientProtocol`` PLUS ``rates()`` (the one extra method
    ``MT5OHLCVProvider`` needs) with REAL ``MT5Client`` lifecycle fidelity -
    every initialized-only method raises ``MT5NotInitializedError`` (never
    ``MarketDataError``, never a graceful ``"UNAVAILABLE"``) until
    ``initialize()`` has actually reached a non-``INITIALIZATION_FAILED``/
    ``LOGIN_FAILED`` state, exactly mirroring ``app.mt5.client.MT5Client``'s
    own ``_initialized`` flag semantics.

    A single shared ``call_log`` records every method call, across BOTH the
    Technical MT5 OHLCV read path (``rates()``) and every runtime MT5 read
    (``account_facts``/``positions``/``history_deals``/``symbol_facts``) in
    the exact order they happened - so a test can assert their real relative
    ordering, not just individual call counts."""

    def __init__(
        self,
        *,
        runtime_status: MT5RuntimeStatus | None = None,
        account_facts: MT5AccountFacts | None = None,
        positions_result: tuple[str, tuple] = ("OK", ()),
        history_deals_result: tuple[str, tuple] = ("OK", ()),
        symbol_facts_by_symbol: dict[str, object] | None = None,
        rates_result: tuple[str, tuple] = ("OK", ()),
    ) -> None:
        self._runtime_status = runtime_status or MT5RuntimeStatus(as_of=datetime.now(UTC), state=MT5ConnectivityState.AVAILABLE)
        self._account_facts = account_facts
        self._positions_result = positions_result
        self._history_deals_result = history_deals_result
        self._symbol_facts_by_symbol = symbol_facts_by_symbol or {}
        self._rates_result = rates_result
        self._initialized = False

        self.call_log: list[str] = []
        self.initialize_calls = 0
        self.shutdown_calls = 0

    def _require_initialized(self, name: str) -> None:
        # Logged BEFORE the check, deliberately: the call was genuinely
        # attempted even when it then raises - a test asserting "this
        # method was attempted" must see it in ``call_log`` regardless of
        # outcome, mirroring what a real caller observes (it DID call the
        # method; the method chose to raise).
        self.call_log.append(name)
        if not self._initialized:
            raise MT5NotInitializedError(f"{name}() called before a successful initialize()")

    def initialize(self) -> MT5RuntimeStatus:
        self.initialize_calls += 1
        self.call_log.append("initialize")
        if self._runtime_status.state not in (MT5ConnectivityState.INITIALIZATION_FAILED, MT5ConnectivityState.LOGIN_FAILED):
            self._initialized = True
        return self._runtime_status

    def runtime_status(self) -> MT5RuntimeStatus:
        self._require_initialized("runtime_status")
        return self._runtime_status

    def account_facts(self) -> MT5AccountFacts | None:
        self._require_initialized("account_facts")
        return self._account_facts

    def positions(self) -> tuple[str, tuple]:
        self._require_initialized("positions")
        return self._positions_result

    def history_deals(self, *, start: object, end: object) -> tuple[str, tuple]:
        self._require_initialized("history_deals")
        return self._history_deals_result

    def symbol_facts(self, symbol: str) -> object | None:
        self._require_initialized("symbol_facts")
        return self._symbol_facts_by_symbol.get(symbol)

    def rates(self, *, symbol: str, timeframe: object, count: int) -> tuple[str, tuple]:
        self._require_initialized("rates")
        if self._runtime_status.state is not MT5ConnectivityState.AVAILABLE:
            # Mirrors the real ``MT5Client.rates()``'s own re-check: once
            # initialized, a since-degraded connection (``TERMINAL_UNAVAILABLE``/
            # ``ACCOUNT_UNAVAILABLE``) reports "UNAVAILABLE" gracefully -
            # never ``MT5NotInitializedError`` - so Technical's own
            # per-timeframe ``except MarketDataError`` catches it normally.
            return "UNAVAILABLE", ()
        return self._rates_result

    def shutdown(self) -> None:
        self.shutdown_calls += 1
        self.call_log.append("shutdown")
        self._initialized = False


class FakeRecordPersistence:
    """In-memory stand-in for ``MT5RecommendationPersistence``/
    ``MT5RecommendationProvenancePersistence`` - same three-method surface,
    with per-``trade_id`` forced read statuses for exercising
    VALID/CORRUPT/UNAVAILABLE preflight paths without real corrupted files."""

    def __init__(self) -> None:
        self._forced_status: dict[str, ReadStatus] = {}
        self._store: dict[str, object] = {}
        self.write_calls: list[tuple[str, object]] = []

    def force_status(self, trade_id: str, status: ReadStatus) -> None:
        self._forced_status[trade_id] = status

    def read(self, trade_id: str) -> tuple[ReadStatus, object | None]:
        forced = self._forced_status.get(trade_id)
        if forced is not None and forced != "VALID":
            return forced, None
        if trade_id in self._store:
            return "VALID", self._store[trade_id]
        return "ABSENT", None

    def write(self, trade_id: str, value: object) -> bool:
        self.write_calls.append((trade_id, value))
        self._store[trade_id] = value
        return True

    def list_trade_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._store))


class RaisingExplanationClient:
    def explain(self, request: object) -> object:
        raise RuntimeError("fake LLM unavailable")


__all__ = [
    "AS_OF",
    "FakeFlowBootstrap",
    "FakeMT5Client",
    "FakeRecordPersistence",
    "FakeTechnicalComposer",
    "LifecycleTrackingMT5Client",
    "RaisingExplanationClient",
    "all_trade_ids",
    "build_config",
]
