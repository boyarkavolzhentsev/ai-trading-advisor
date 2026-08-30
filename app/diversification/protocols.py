"""Uniform entry point the Stage 8 Portfolio/Diversification Supervisor
implements.

Mirrors ``app.risk.protocols.RiskGateProtocol`` one layer up: a stateless,
synchronous, provider-agnostic function of one already-produced
``StrategyRiskResult``. No account snapshot, no config, no candidate-input
argument (both account facts and the portfolio-risk percentage are already
embedded on ``strategy_risk_result``), no history argument, no storage, no
network.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.core.models.portfolio_result import StrategyPortfolioResult
from app.core.models.risk_gate_result import StrategyRiskResult


@runtime_checkable
class PortfolioSupervisorProtocol(Protocol):
    """Stateless, synchronous, provider-agnostic Stage 8 portfolio gate."""

    def evaluate(self, *, strategy_risk_result: StrategyRiskResult) -> StrategyPortfolioResult: ...


__all__ = ["PortfolioSupervisorProtocol"]
