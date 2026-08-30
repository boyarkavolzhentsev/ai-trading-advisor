"""Uniform entry point the Stage 7 Money/Risk Management Gate implements.

Mirrors ``app.decision.protocols.PolicyGateProtocol`` one layer up: a
stateless, synchronous, provider-agnostic function of one already-produced
``StrategyPolicyResult`` plus explicit account-risk inputs. No history
argument, no storage, no network, no wall-clock argument (``as_of`` lives on
``AccountRiskSnapshot`` itself).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.core.config.trading_cycle import TradingCycleConfig
from app.core.models.policy_gate_result import StrategyPolicyResult
from app.core.models.risk_gate_result import AccountRiskSnapshot, CandidateRiskInput, StrategyRiskResult


@runtime_checkable
class RiskGateProtocol(Protocol):
    """Stateless, synchronous, provider-agnostic Stage 7 risk gate."""

    def evaluate(
        self,
        *,
        strategy_policy_result: StrategyPolicyResult,
        account_snapshot: AccountRiskSnapshot,
        candidate_inputs: tuple[CandidateRiskInput, ...],
        trading_cycle_config: TradingCycleConfig,
    ) -> StrategyRiskResult: ...


__all__ = ["RiskGateProtocol"]
