"""Uniform entry points the Stage 9 Statistics/Session components implement.

Mirrors ``app.diversification.protocols.PortfolioSupervisorProtocol`` one
layer up: stateless, synchronous, provider-agnostic functions of their own
explicit inputs. No history argument beyond what each protocol's own input
already is, no storage, no network, no MT5.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.core.models.performance import PerformanceSnapshot
from app.core.models.portfolio_result import StrategyPortfolioResult
from app.core.models.position import PositionRecord
from app.core.models.session_result import StrategySessionResult


@runtime_checkable
class SessionGateProtocol(Protocol):
    """Stateless, synchronous, provider-agnostic Stage 9 session gate."""

    def evaluate(
        self, *, strategy_portfolio_result: StrategyPortfolioResult, locked_override: bool = False
    ) -> StrategySessionResult: ...


@runtime_checkable
class StatisticsAggregatorProtocol(Protocol):
    """Stateless, synchronous, provider-agnostic Stage 9 statistics
    aggregator. Reporting only - its output never feeds ``SessionGateProtocol``."""

    def aggregate(self, *, records: tuple[PositionRecord, ...]) -> PerformanceSnapshot: ...


__all__ = ["SessionGateProtocol", "StatisticsAggregatorProtocol"]
