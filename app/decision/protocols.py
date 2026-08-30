"""Uniform entry point the Stage 6C Policy/Safety Gate implements.

Mirrors ``app.judge.protocols.JudgeProtocol`` one layer up: a stateless,
synchronous, provider-agnostic function of one already-produced
``StrategyJudgeResult``. No timestamp argument (the authoritative time
remains
``strategy_judge_result.strategy_router_result.market_evaluation.evaluation_time``),
no config, no history argument, no storage, no network.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.core.models.policy_gate_result import StrategyPolicyResult
from app.core.models.strategy_judge_result import StrategyJudgeResult


@runtime_checkable
class PolicyGateProtocol(Protocol):
    """Stateless, synchronous, provider-agnostic Stage 6C policy gate."""

    def apply(self, *, strategy_judge_result: StrategyJudgeResult) -> StrategyPolicyResult: ...


__all__ = ["PolicyGateProtocol"]
