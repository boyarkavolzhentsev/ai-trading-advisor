"""Uniform entry point the read-only MT5 adapter implements.

Mirrors ``app.risk.protocols.RiskGateProtocol``/``app.diversification.
protocols.PortfolioSupervisorProtocol`` one architectural layer over: a
narrow, explicit surface a fake implementation can satisfy without
MetaTrader5 installed, so every pure Stage 10 test and every future Stage
10E consumer depends on this protocol, never on ``app.mt5.client`` directly.
Deliberately excludes any order-placement method and any order-history
method - ``history_deals()`` (Stage 10D) is the sole history surface added
so far, added only once Stage 10D actually needed it; nothing beyond it is
pre-declared here.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.core.models.base import Timestamp
from app.core.models.mt5_history import MT5Deal
from app.core.models.mt5_position import MT5Position
from app.core.models.mt5_runtime import MT5AccountFacts, MT5RuntimeStatus
from app.core.models.mt5_symbol import MT5SymbolFacts
from app.mt5.history import MT5HistoryReadStatus
from app.mt5.risk import MT5PositionsReadStatus


@runtime_checkable
class MT5ClientProtocol(Protocol):
    """Stateless-per-call, read-only MT5 adapter.

    ``initialize()`` and ``runtime_status()`` never raise for a legitimate
    broker/terminal/account condition - every such condition is a typed
    state on the returned value. ``account_facts()``/``symbol_facts()``
    return ``None`` whenever the fact is not legitimately available, never a
    fabricated one. ``positions()``/``history_deals()`` distinguish a
    confirmed-empty read (``"OK"`` with an empty tuple) from an unavailable
    one (``"UNAVAILABLE"``) - never fabricate "confirmed zero" when
    connectivity, or one raw item's own normalization, is actually unsafe.
    """

    def initialize(self) -> MT5RuntimeStatus: ...

    def runtime_status(self) -> MT5RuntimeStatus: ...

    def account_facts(self) -> MT5AccountFacts | None: ...

    def positions(self) -> tuple[MT5PositionsReadStatus, tuple[MT5Position, ...]]: ...

    def symbol_facts(self, symbol: str) -> MT5SymbolFacts | None: ...

    def history_deals(self, *, start: Timestamp, end: Timestamp) -> tuple[MT5HistoryReadStatus, tuple[MT5Deal, ...]]: ...

    def shutdown(self) -> None: ...


__all__ = ["MT5ClientProtocol"]
