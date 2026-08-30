"""Shared builders for Stage 7 risk-gate tests.

Builds real ``StrategyPolicyResult`` fixtures via the real
``StrategyRouter``/``Judge``/``PolicyGate`` chain (reusing
``tests/policy_gate_support.py`` and its own upstream support modules), then
runs them through the real ``RiskGate`` - never a hand-rolled
``StrategyRiskResult`` for anything but malformed-model invariant/error
tests. Not a test module itself (no ``test_`` prefix): pytest will not
collect it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.core.config.trading_cycle import TradingCycleConfig
from app.core.enums.policy_gate import PolicyFamilyVerdict
from app.core.models.policy_gate_result import StrategyPolicyResult
from app.core.models.risk_gate_result import AccountRiskSnapshot, CandidateRiskInput, StrategyRiskResult
from app.risk.engine import RiskGate
from tests.policy_gate_support import route_judge_and_gate

__all__ = [
    "NOW",
    "default_account_snapshot",
    "default_config",
    "default_candidates_for",
    "route_judge_gate_and_risk",
]

NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


def default_config(**overrides: object) -> TradingCycleConfig:
    return TradingCycleConfig(**overrides)


def default_account_snapshot(**overrides: object) -> AccountRiskSnapshot:
    fields: dict[str, object] = {
        "as_of": NOW,
        "rollover_equity": Decimal("100000"),
        "current_equity": Decimal("100000"),
        "realized_daily_pnl": Decimal("0"),
        "floating_pnl": Decimal("0"),
        "current_open_risk_to_stop": Decimal("0"),
    }
    fields.update(overrides)
    return AccountRiskSnapshot(**fields)


def default_candidates_for(
    strategy_policy_result: StrategyPolicyResult, *, risk_per_unit: Decimal = Decimal("10")
) -> tuple[CandidateRiskInput, ...]:
    """One ``CandidateRiskInput`` with the given ``risk_per_unit`` for every
    Policy-eligible family in ``strategy_policy_result`` - none for blocked
    families."""
    return tuple(
        CandidateRiskInput(family=result.family, risk_per_unit=risk_per_unit)
        for result in strategy_policy_result.family_results
        if result.verdict is PolicyFamilyVerdict.ELIGIBLE_FOR_RISK_REVIEW
    )


def route_judge_gate_and_risk(
    *,
    account_snapshot: AccountRiskSnapshot | None = None,
    trading_cycle_config: TradingCycleConfig | None = None,
    candidate_inputs: tuple[CandidateRiskInput, ...] | None = None,
    risk_per_unit: Decimal = Decimal("10"),
    **evaluate_kwargs: object,
) -> tuple[StrategyPolicyResult, StrategyRiskResult]:
    _, _, policy_result = route_judge_and_gate(**evaluate_kwargs)
    snapshot = account_snapshot if account_snapshot is not None else default_account_snapshot()
    config = trading_cycle_config if trading_cycle_config is not None else default_config()
    candidates = (
        candidate_inputs if candidate_inputs is not None else default_candidates_for(policy_result, risk_per_unit=risk_per_unit)
    )
    risk_result = RiskGate().evaluate(
        strategy_policy_result=policy_result,
        account_snapshot=snapshot,
        candidate_inputs=candidates,
        trading_cycle_config=config,
    )
    return policy_result, risk_result
