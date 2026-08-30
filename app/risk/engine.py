"""Deterministic Money/Risk Management Gate (Stage 7).

Applies deterministic account-level risk policy over one already-produced
``StrategyPolicyResult``: whether each family Policy produced a result for is
structurally and account-risk-wise allowed to proceed to Stage 8 Portfolio/
Diversification review, and if so a deterministic per-candidate risk ceiling
and generic unit-size recommendation. Never invokes Router/Judge/Policy,
never touches a Flow/Technical/External Intelligence analyst or supervisor
package, never performs I/O - a pure, synchronous, stateless function of its
four explicit inputs (see ``app.risk.protocols.RiskGateProtocol``).

Reads only ``PolicyFamilyVerdict``, the caller-supplied ``AccountRiskSnapshot``
and ``TradingCycleConfig``, and each candidate's opaque ``risk_per_unit`` -
never a Flow/Technical/External Intelligence observation, never a Judge
``direction``. Whether a family's account-risk ceiling permits proceeding is
exactly the information this gate is allowed to act on; what any evidence
means, or which direction a family favors, is Stage 6B/6C's question,
answered upstream, never re-asked here.

Every Policy-eligible family is evaluated entirely independently against the
*same* ``AccountRiskSnapshot``: no budget is reserved, subtracted, or
sequenced between family results, mirroring Policy's own no-cross-family-
voting discipline two stages over. ``RiskFamilyResult.max_individual_risk``
is an independent per-candidate ceiling, never a joint-safe allocation -
Stage 7 makes no simultaneous-allocation guarantee across families.
"""

from __future__ import annotations

from decimal import Decimal

from app.core.config.trading_cycle import TradingCycleConfig
from app.core.enums.policy_gate import PolicyFamilyVerdict
from app.core.enums.risk_gate import RiskBlockReason, RiskFamilyVerdict, RiskGateOutcome
from app.core.enums.strategy_router import StrategyFamily
from app.core.models.policy_gate_result import PolicyFamilyResult, StrategyPolicyResult
from app.core.models.risk_gate_result import AccountRiskSnapshot, CandidateRiskInput, RiskFamilyResult, StrategyRiskResult
from app.money_management.sizing import calculate_recommended_units
from app.risk.errors import (
    CandidateForBlockedFamilyError,
    DuplicateCandidateFamilyError,
    MissingCandidateForEligibleFamilyError,
    UnknownCandidateFamilyError,
)

_REASON_ORDER: tuple[RiskBlockReason, ...] = tuple(RiskBlockReason)


def _account_risk_state(
    account_snapshot: AccountRiskSnapshot, trading_cycle_config: TradingCycleConfig
) -> tuple[Decimal, Decimal, Decimal]:
    """A locally-owned copy of the account-risk arithmetic - not imported
    from ``app.core.models.risk_gate_result`` (whose own model validator
    independently re-derives the identical figures to self-validate its own
    fields), mirroring the Stage 5A/6A/6C precedent of the operational
    component and the result model's self-validation maintaining independent
    copies of the same primitive rather than cross-importing one from the
    other."""
    daily_loss_limit = account_snapshot.rollover_equity * (trading_cycle_config.daily_risk_limit_percent / Decimal("100"))
    current_daily_pnl = account_snapshot.realized_daily_pnl + account_snapshot.floating_pnl
    loss_consumed = max(Decimal("0"), -current_daily_pnl)
    remaining_daily_loss_capacity = max(Decimal("0"), daily_loss_limit - loss_consumed)
    available_new_trade_risk = max(Decimal("0"), remaining_daily_loss_capacity - account_snapshot.current_open_risk_to_stop)
    per_trade_risk_budget = account_snapshot.rollover_equity * (trading_cycle_config.per_trade_risk_limit_percent / Decimal("100"))
    return remaining_daily_loss_capacity, available_new_trade_risk, per_trade_risk_budget


def _validate_candidate_inputs(
    strategy_policy_result: StrategyPolicyResult, candidate_inputs: tuple[CandidateRiskInput, ...]
) -> None:
    policy_by_family: dict[StrategyFamily, PolicyFamilyResult] = {
        result.family: result for result in strategy_policy_result.family_results
    }

    seen: set[StrategyFamily] = set()
    for candidate in candidate_inputs:
        if candidate.family in seen:
            raise DuplicateCandidateFamilyError(f"duplicate CandidateRiskInput for family {candidate.family}")
        seen.add(candidate.family)

        policy_result = policy_by_family.get(candidate.family)
        if policy_result is None:
            raise UnknownCandidateFamilyError(
                f"CandidateRiskInput references family {candidate.family} absent from strategy_policy_result"
            )
        if policy_result.verdict is PolicyFamilyVerdict.BLOCKED:
            raise CandidateForBlockedFamilyError(
                f"CandidateRiskInput references Policy-BLOCKED family {candidate.family}"
            )

    for policy_result in strategy_policy_result.family_results:
        if policy_result.verdict is PolicyFamilyVerdict.ELIGIBLE_FOR_RISK_REVIEW and policy_result.family not in seen:
            raise MissingCandidateForEligibleFamilyError(
                f"no CandidateRiskInput supplied for Policy-eligible family {policy_result.family}"
            )


def _evaluate_family(
    policy_result: PolicyFamilyResult,
    candidate: CandidateRiskInput | None,
    remaining_daily_loss_capacity: Decimal,
    available_new_trade_risk: Decimal,
    per_trade_risk_budget: Decimal,
) -> RiskFamilyResult:
    if policy_result.verdict is PolicyFamilyVerdict.BLOCKED:
        return RiskFamilyResult(
            family=policy_result.family,
            verdict=RiskFamilyVerdict.BLOCKED_BY_RISK,
            reasons=(RiskBlockReason.POLICY_NOT_ELIGIBLE,),
        )

    assert candidate is not None  # guaranteed by _validate_candidate_inputs

    reason_set: set[RiskBlockReason] = set()
    if candidate.risk_per_unit <= 0:
        reason_set.add(RiskBlockReason.ZERO_OR_NEGATIVE_RISK_PER_UNIT)
    if remaining_daily_loss_capacity <= 0:
        reason_set.add(RiskBlockReason.DAILY_LOSS_LIMIT_REACHED)
    elif available_new_trade_risk <= 0:
        reason_set.add(RiskBlockReason.INSUFFICIENT_REMAINING_RISK_BUDGET)

    reasons = tuple(reason for reason in _REASON_ORDER if reason in reason_set)
    if reasons:
        return RiskFamilyResult(family=policy_result.family, verdict=RiskFamilyVerdict.BLOCKED_BY_RISK, reasons=reasons)

    max_individual_risk = min(per_trade_risk_budget, available_new_trade_risk)
    recommended_units = calculate_recommended_units(
        max_individual_risk=max_individual_risk, risk_per_unit=candidate.risk_per_unit
    )
    return RiskFamilyResult(
        family=policy_result.family,
        verdict=RiskFamilyVerdict.ELIGIBLE_FOR_PORTFOLIO_REVIEW,
        max_individual_risk=max_individual_risk,
        recommended_units=recommended_units,
    )


class RiskGate:
    """Deterministic Stage 7 aggregator over one ``StrategyPolicyResult``."""

    def evaluate(
        self,
        *,
        strategy_policy_result: StrategyPolicyResult,
        account_snapshot: AccountRiskSnapshot,
        candidate_inputs: tuple[CandidateRiskInput, ...],
        trading_cycle_config: TradingCycleConfig,
    ) -> StrategyRiskResult:
        _validate_candidate_inputs(strategy_policy_result, candidate_inputs)

        candidate_by_family = {candidate.family: candidate for candidate in candidate_inputs}
        remaining_daily_loss_capacity, available_new_trade_risk, per_trade_risk_budget = _account_risk_state(
            account_snapshot, trading_cycle_config
        )

        family_results = tuple(
            _evaluate_family(
                policy_result,
                candidate_by_family.get(policy_result.family),
                remaining_daily_loss_capacity,
                available_new_trade_risk,
                per_trade_risk_budget,
            )
            for policy_result in strategy_policy_result.family_results
        )
        any_eligible = any(result.verdict is RiskFamilyVerdict.ELIGIBLE_FOR_PORTFOLIO_REVIEW for result in family_results)
        outcome = (
            RiskGateOutcome.SOME_ELIGIBLE_FOR_PORTFOLIO_REVIEW if any_eligible else RiskGateOutcome.NO_RISK_ELIGIBLE_FAMILY
        )

        return StrategyRiskResult(
            strategy_policy_result=strategy_policy_result,
            trading_cycle_config=trading_cycle_config,
            account_snapshot=account_snapshot,
            candidate_inputs=candidate_inputs,
            outcome=outcome,
            family_results=family_results,
        )


__all__ = ["RiskGate"]
