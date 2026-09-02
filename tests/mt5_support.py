"""Shared fakes for Stage 10A MT5 adapter tests.

Two distinct fakes, at two distinct boundaries:

- ``FakeRawMT5Module`` stands in for the real ``MetaTrader5`` package itself
  (injected into ``MT5Client(mt5_module=...)``), so ``app.mt5.client``'s own
  normalization/mapping logic is exercised without the real package
  installed.
- ``FakeMT5Client`` implements ``MT5ClientProtocol`` directly, standing in
  for the whole adapter for any test/consumer that only needs the
  normalized surface (mirrors ``tests/risk_gate_support.py``'s own
  real-chain-vs-hand-built-fixture split one architectural layer over).

Not a test module itself (no ``test_`` prefix): pytest will not collect it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from app.core.enums.mt5_runtime import MT5ConnectivityState
from app.core.models.mt5_runtime import MT5AccountFacts, MT5RuntimeStatus

__all__ = [
    "FakeMT5Client",
    "FakeRawMT5Module",
    "default_account_info",
    "default_terminal_info",
]

NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


def default_terminal_info(*, connected: bool = True) -> SimpleNamespace:
    return SimpleNamespace(connected=connected)


def default_account_info(
    *,
    equity: float = 100000.0,
    balance: float = 100000.0,
    margin: float = 0.0,
    margin_free: float = 100000.0,
    margin_level: float = 0.0,
    currency: str = "USD",
    trade_allowed: bool = True,
    trade_expert: bool = True,
    margin_mode: int = 0,
    profit: float = 0.0,
) -> SimpleNamespace:
    return SimpleNamespace(
        equity=equity,
        balance=balance,
        margin=margin,
        margin_free=margin_free,
        margin_level=margin_level,
        currency=currency,
        trade_allowed=trade_allowed,
        trade_expert=trade_expert,
        margin_mode=margin_mode,
        profit=profit,
    )


class FakeRawMT5Module:
    """Stands in for the ``MetaTrader5`` package's own module-level surface.

    Raw ``ACCOUNT_MARGIN_MODE_*``/``POSITION_TYPE_*``/``SYMBOL_TRADE_MODE_*``
    values mirror the real package's actual integer constants exactly (not
    arbitrary fakes), so the mapping tests exercise the real values
    ``app.mt5.client`` will see in production.
    """

    ACCOUNT_MARGIN_MODE_RETAIL_NETTING = 0
    ACCOUNT_MARGIN_MODE_EXCHANGE = 1
    ACCOUNT_MARGIN_MODE_RETAIL_HEDGING = 2

    POSITION_TYPE_BUY = 0
    POSITION_TYPE_SELL = 1

    SYMBOL_TRADE_MODE_DISABLED = 0
    SYMBOL_TRADE_MODE_LONGONLY = 1
    SYMBOL_TRADE_MODE_SHORTONLY = 2
    SYMBOL_TRADE_MODE_CLOSEONLY = 3
    SYMBOL_TRADE_MODE_FULL = 4

    _UNSET: Any = object()

    def __init__(
        self,
        *,
        initialize_result: bool = True,
        terminal_info: SimpleNamespace | None = _UNSET,
        account_info: SimpleNamespace | None = _UNSET,
        last_error: tuple[int, str] | None = (1, "Success"),
        positions: tuple[SimpleNamespace, ...] | None = (),
        symbol_info_result: SimpleNamespace | None = None,
        symbol_tick_result: SimpleNamespace | None = None,
    ) -> None:
        self._initialize_result = initialize_result
        self._terminal_info = default_terminal_info() if terminal_info is self._UNSET else terminal_info
        self._account_info = default_account_info() if account_info is self._UNSET else account_info
        self._last_error = last_error
        self._positions = positions
        self._symbol_info_result = symbol_info_result
        self._symbol_tick_result = symbol_tick_result
        self.initialize_calls: list[dict[str, Any]] = []
        self.shutdown_calls = 0
        self.symbol_info_calls: list[str] = []
        self.symbol_info_tick_calls: list[str] = []

    def initialize(self, **kwargs: Any) -> bool:
        self.initialize_calls.append(kwargs)
        return self._initialize_result

    def terminal_info(self) -> SimpleNamespace | None:
        return self._terminal_info

    def account_info(self) -> SimpleNamespace | None:
        return self._account_info

    def positions_get(self) -> tuple[SimpleNamespace, ...] | None:
        return self._positions

    def symbol_info(self, symbol: str) -> SimpleNamespace | None:
        self.symbol_info_calls.append(symbol)
        return self._symbol_info_result

    def symbol_info_tick(self, symbol: str) -> SimpleNamespace | None:
        self.symbol_info_tick_calls.append(symbol)
        return self._symbol_tick_result

    def shutdown(self) -> None:
        self.shutdown_calls += 1

    def last_error(self) -> tuple[int, str] | None:
        return self._last_error


class FakeMT5Client:
    """Directly implements ``MT5ClientProtocol`` - no raw MT5 concept at all."""

    def __init__(
        self,
        *,
        statuses: list[MT5RuntimeStatus] | None = None,
        account_facts: MT5AccountFacts | None = None,
        positions_result: tuple[str, tuple[Any, ...]] = ("OK", ()),
        symbol_facts_result: Any | None = None,
    ) -> None:
        self._statuses = statuses or [MT5RuntimeStatus(as_of=NOW, state=MT5ConnectivityState.AVAILABLE)]
        self._account_facts = account_facts
        self._positions_result = positions_result
        self._symbol_facts_result = symbol_facts_result
        self._call_index = 0

    def initialize(self) -> MT5RuntimeStatus:
        return self._next_status()

    def runtime_status(self) -> MT5RuntimeStatus:
        return self._next_status()

    def account_facts(self) -> MT5AccountFacts | None:
        return self._account_facts

    def positions(self) -> tuple[str, tuple[Any, ...]]:
        return self._positions_result

    def symbol_facts(self, symbol: str) -> Any | None:
        return self._symbol_facts_result

    def shutdown(self) -> None:
        return None

    def _next_status(self) -> MT5RuntimeStatus:
        status = self._statuses[min(self._call_index, len(self._statuses) - 1)]
        self._call_index += 1
        return status
