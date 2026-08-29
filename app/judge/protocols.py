"""Uniform entry point the Stage 6B Judge implements.

Mirrors ``app.strategies.protocols.StrategyRouterProtocol`` one layer up: a
stateless, synchronous, provider-agnostic function of one already-produced
``StrategyRouterResult``. No timestamp argument (the authoritative time
remains ``strategy_router_result.market_evaluation.evaluation_time``), no
config, no history argument, no storage, no network.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.core.models.strategy_judge_result import StrategyJudgeResult
from app.core.models.strategy_router_result import StrategyRouterResult


@runtime_checkable
class JudgeProtocol(Protocol):
    """Stateless, synchronous, provider-agnostic Stage 6B judge."""

    def judge(self, *, strategy_router_result: StrategyRouterResult) -> StrategyJudgeResult: ...


__all__ = ["JudgeProtocol"]
