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
    )


class FakeRawMT5Module:
    """Stands in for the ``MetaTrader5`` package's own module-level surface.

    Raw ``ACCOUNT_MARGIN_MODE_*`` values mirror the real package's actual
    integer constants exactly (not arbitrary fakes), so the mapping test
    exercises the real values ``app.mt5.client`` will see in production.
    """

    ACCOUNT_MARGIN_MODE_RETAIL_NETTING = 0
    ACCOUNT_MARGIN_MODE_EXCHANGE = 1
    ACCOUNT_MARGIN_MODE_RETAIL_HEDGING = 2

    _UNSET: Any = object()

    def __init__(
        self,
        *,
        initialize_result: bool = True,
        terminal_info: SimpleNamespace | None = _UNSET,
        account_info: SimpleNamespace | None = _UNSET,
        last_error: tuple[int, str] | None = (1, "Success"),
    ) -> None:
        self._initialize_result = initialize_result
        self._terminal_info = default_terminal_info() if terminal_info is self._UNSET else terminal_info
        self._account_info = default_account_info() if account_info is self._UNSET else account_info
        self._last_error = last_error
        self.initialize_calls: list[dict[str, Any]] = []
        self.shutdown_calls = 0

    def initialize(self, **kwargs: Any) -> bool:
        self.initialize_calls.append(kwargs)
        return self._initialize_result

    def terminal_info(self) -> SimpleNamespace | None:
        return self._terminal_info

    def account_info(self) -> SimpleNamespace | None:
        return self._account_info

    def shutdown(self) -> None:
        self.shutdown_calls += 1

    def last_error(self) -> tuple[int, str] | None:
        return self._last_error


class FakeMT5Client:
    """Directly implements ``MT5ClientProtocol`` - no raw MT5 concept at all."""

    def __init__(self, *, statuses: list[MT5RuntimeStatus] | None = None, account_facts: MT5AccountFacts | None = None) -> None:
        self._statuses = statuses or [MT5RuntimeStatus(as_of=NOW, state=MT5ConnectivityState.AVAILABLE)]
        self._account_facts = account_facts
        self._call_index = 0

    def initialize(self) -> MT5RuntimeStatus:
        return self._next_status()

    def runtime_status(self) -> MT5RuntimeStatus:
        return self._next_status()

    def account_facts(self) -> MT5AccountFacts | None:
        return self._account_facts

    def shutdown(self) -> None:
        return None

    def _next_status(self) -> MT5RuntimeStatus:
        status = self._statuses[min(self._call_index, len(self._statuses) - 1)]
        self._call_index += 1
        return status
