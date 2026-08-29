"""Uniform entry point the Stage 6A Strategy Router implements.

Mirrors ``app.market_evaluation.protocols.MarketEvaluationProtocol`` one
layer up: a stateless, synchronous, provider-agnostic function of one
already-produced ``MarketEvaluationResult``. No timestamp argument (the
authoritative time is ``market_evaluation.evaluation_time``), no history
argument, no storage, no network/provider methods, no configuration.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.core.models.market_evaluation_result import MarketEvaluationResult
from app.core.models.strategy_router_result import StrategyRouterResult


@runtime_checkable
class StrategyRouterProtocol(Protocol):
    """Stateless, synchronous, provider-agnostic Stage 6A router."""

    def route(self, *, market_evaluation: MarketEvaluationResult) -> StrategyRouterResult: ...


__all__ = ["StrategyRouterProtocol"]
