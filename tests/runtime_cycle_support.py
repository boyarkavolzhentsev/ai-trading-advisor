"""Shared fixtures for Part F Runtime Cycle Orchestration tests.

``RuntimeCycleFakeClient`` implements ``MT5ClientProtocol`` directly (no raw
MT5 concept at all) with per-call tracking so tests can assert exact call
counts (``positions()``/``history_deals()`` at most once per cycle,
``symbol_facts()`` at most once per unique symbol) - something
``tests.mt5_support.FakeMT5Client`` does not itself track.

Not a test module itself (no ``test_`` prefix): pytest will not collect it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.core.enums.mt5_runtime import AccountPositionMode, MT5ConnectivityState
from app.core.models.base import Timestamp
from app.core.models.mt5_history import MT5Deal
from app.core.models.mt5_position import MT5Position
from app.core.models.mt5_runtime import MT5AccountFacts, MT5RuntimeStatus
from app.core.models.mt5_symbol import MT5SymbolFacts

__all__ = [
    "AS_OF",
    "TRADING_DAY_KEY",
    "RuntimeCycleFakeClient",
    "default_account_facts",
    "default_rollover_policy",
]

AS_OF: Timestamp = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
TRADING_DAY_KEY = "2026-01-01"


def default_account_facts(**overrides: object) -> MT5AccountFacts:
    fields: dict[str, object] = {
        "as_of": AS_OF,
        "equity": Decimal("100000"),
        "balance": Decimal("100000"),
        "margin": Decimal("0"),
        "margin_free": Decimal("100000"),
        "margin_level": None,
        "currency": "USD",
        "trade_allowed": True,
        "trade_expert": True,
        "margin_mode": AccountPositionMode.HEDGING,
        "floating_pnl": Decimal("0"),
    }
    fields.update(overrides)
    return MT5AccountFacts(**fields)


def default_rollover_policy() -> Any:
    from app.core.config.mt5_rollover import MT5RolloverPolicyConfig

    return MT5RolloverPolicyConfig(rollover_timezone="UTC", rollover_hour=0)


class RuntimeCycleFakeClient:
    """Directly implements ``MT5ClientProtocol``, tracking every call so
    read-once/dedup invariants can be asserted precisely."""

    def __init__(
        self,
        *,
        runtime_status: MT5RuntimeStatus | None = None,
        account_facts: MT5AccountFacts | None = None,
        positions_result: tuple[str, tuple[MT5Position, ...]] = ("OK", ()),
        symbol_facts_by_symbol: dict[str, MT5SymbolFacts] | None = None,
        history_deals_result: tuple[str, tuple[MT5Deal, ...]] = ("OK", ()),
    ) -> None:
        self._runtime_status = runtime_status or MT5RuntimeStatus(as_of=AS_OF, state=MT5ConnectivityState.AVAILABLE)
        self._account_facts = account_facts
        self._positions_result = positions_result
        self._symbol_facts_by_symbol = symbol_facts_by_symbol or {}
        self._history_deals_result = history_deals_result

        self.initialize_calls = 0
        self.positions_calls = 0
        self.symbol_facts_calls: list[str] = []
        self.history_deals_calls: list[tuple[Timestamp, Timestamp]] = []
        self.shutdown_calls = 0

    def initialize(self) -> MT5RuntimeStatus:
        self.initialize_calls += 1
        return self._runtime_status

    def runtime_status(self) -> MT5RuntimeStatus:
        return self._runtime_status

    def account_facts(self) -> MT5AccountFacts | None:
        return self._account_facts

    def positions(self) -> tuple[str, tuple[MT5Position, ...]]:
        self.positions_calls += 1
        return self._positions_result

    def symbol_facts(self, symbol: str) -> MT5SymbolFacts | None:
        self.symbol_facts_calls.append(symbol)
        return self._symbol_facts_by_symbol.get(symbol)

    def history_deals(self, *, start: Timestamp, end: Timestamp) -> tuple[str, tuple[MT5Deal, ...]]:
        self.history_deals_calls.append((start, end))
        return self._history_deals_result

    def shutdown(self) -> None:
        self.shutdown_calls += 1
