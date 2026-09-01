"""Uniform entry point the Stage 10A MT5 read-only adapter implements.

Mirrors ``app.risk.protocols.RiskGateProtocol``/``app.diversification.
protocols.PortfolioSupervisorProtocol`` one architectural layer over: a
narrow, explicit surface a fake implementation can satisfy without
MetaTrader5 installed, so every pure Stage 10A test and every future Stage
10B-E consumer depends on this protocol, never on ``app.mt5.client``
directly. Deliberately excludes ``open_positions``, ``symbol_specification``,
any history method, and any order-placement method - those belong to a later
Stage 10 sub-stage and are added to this same protocol only when that
sub-stage actually needs them, never pre-declared here.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.core.models.mt5_runtime import MT5AccountFacts, MT5RuntimeStatus


@runtime_checkable
class MT5ClientProtocol(Protocol):
    """Stateless-per-call, read-only Stage 10A MT5 adapter.

    ``initialize()`` and ``runtime_status()`` never raise for a legitimate
    broker/terminal/account condition - every such condition is a typed
    ``MT5ConnectivityState`` on the returned ``MT5RuntimeStatus``.
    ``account_facts()`` returns ``None`` whenever the most recent status is
    not ``AVAILABLE``, never a fabricated fact.
    """

    def initialize(self) -> MT5RuntimeStatus: ...

    def runtime_status(self) -> MT5RuntimeStatus: ...

    def account_facts(self) -> MT5AccountFacts | None: ...

    def shutdown(self) -> None: ...


__all__ = ["MT5ClientProtocol"]
