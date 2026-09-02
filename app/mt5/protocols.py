"""Uniform entry point the read-only MT5 adapter implements.

Mirrors ``app.risk.protocols.RiskGateProtocol``/``app.diversification.
protocols.PortfolioSupervisorProtocol`` one architectural layer over: a
narrow, explicit surface a fake implementation can satisfy without
MetaTrader5 installed, so every pure Stage 10 test and every future Stage
10D-E consumer depends on this protocol, never on ``app.mt5.client``
directly. Deliberately excludes any history/deal method and any
order-placement method - those belong to a later Stage 10 sub-stage and are
added to this same protocol only when that sub-stage actually needs them,
never pre-declared here.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.core.models.mt5_position import MT5Position
from app.core.models.mt5_runtime import MT5AccountFacts, MT5RuntimeStatus
from app.core.models.mt5_symbol import MT5SymbolFacts
from app.mt5.risk import MT5PositionsReadStatus


@runtime_checkable
class MT5ClientProtocol(Protocol):
    """Stateless-per-call, read-only MT5 adapter.

    ``initialize()`` and ``runtime_status()`` never raise for a legitimate
    broker/terminal/account condition - every such condition is a typed
    state on the returned value. ``account_facts()``/``symbol_facts()``
    return ``None`` whenever the fact is not legitimately available, never a
    fabricated one. ``positions()`` distinguishes a confirmed-empty read
    (``"OK"`` with an empty tuple) from an unavailable one (``"UNAVAILABLE"``)
    - never fabricates "confirmed zero open positions" when connectivity is
    actually unknown.
    """

    def initialize(self) -> MT5RuntimeStatus: ...

    def runtime_status(self) -> MT5RuntimeStatus: ...

    def account_facts(self) -> MT5AccountFacts | None: ...

    def positions(self) -> tuple[MT5PositionsReadStatus, tuple[MT5Position, ...]]: ...

    def symbol_facts(self, symbol: str) -> MT5SymbolFacts | None: ...

    def shutdown(self) -> None: ...


__all__ = ["MT5ClientProtocol"]
