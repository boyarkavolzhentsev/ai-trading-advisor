"""Shared fakes/builders for Stage 0D Production Advisory Composition tests.

Not a test module itself (no ``test_`` prefix): pytest will not collect it.
Every fake is a narrow, protocol-shaped stand-in - none imports a real SDK,
MT5, or the network.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal

from app.core.config.high_impact_event_bridge import HighImpactEventCalendarTimezoneConfig
from app.core.config.mt5_rollover import MT5RolloverPolicyConfig
from app.core.enums.instrument import ContractType
from app.core.enums.market import MarketType
from app.core.enums.mt5_runtime import MT5ConnectivityState
from app.core.enums.strategy_router import StrategyFamily
from app.core.models.mt5_runtime import MT5RuntimeStatus
from app.core.models.stream_health import StreamHealth
from app.flow.open_interest_poller import TaskHealth, TaskState
from app.flow.realtime_bootstrap import FlowRealtimeBootstrapHealth
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
        "max_price_basis_divergence_percent": Decimal("100"),
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

    def __init__(
        self,
        fetch_failures: tuple[TechnicalFetchFailure, ...] = (),
        *,
        m15_last_closed_close: Decimal | None = Decimal("100"),
    ) -> None:
        self.fetch_failures = fetch_failures
        self.m15_last_closed_close = m15_last_closed_close
        self.build_calls: list[object] = []
        self.sentinel_technical = object()
        self.sentinel_m15 = object()

    def build_technical_result(self, *, as_of: object) -> TechnicalProductionResult:
        self.build_calls.append(as_of)
        return TechnicalProductionResult(
            technical=self.sentinel_technical,  # type: ignore[arg-type]
            m15_market_structure=self.sentinel_m15,  # type: ignore[arg-type]
            m15_last_closed_close=self.m15_last_closed_close,
            fetch_failures=self.fetch_failures,
        )


class FakeMT5Client:
    """Always reports connectivity unavailable - the smallest fake that
    lets a full cycle complete deterministically without touching real
    MT5. Never implements order/execution surfaces (there are none on
    ``MT5ClientProtocol`` to implement)."""

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

    def shutdown(self) -> None:
        pass


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
    "RaisingExplanationClient",
    "all_trade_ids",
    "build_config",
]
