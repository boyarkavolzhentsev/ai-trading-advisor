"""Stage 7 deterministic Money/Risk Management output contract.

Aggregates one already-produced ``StrategyPolicyResult`` plus one explicit
``AccountRiskSnapshot``, one ``TradingCycleConfig``, and a caller-supplied
``CandidateRiskInput`` per Policy-eligible family into a per-family account-
risk verdict: whether that family's Judge/Policy thesis may proceed to Stage
8 Portfolio/Diversification review under the account's daily-loss and
per-trade risk budgets. This model validates structural consistency only by
independently re-deriving the entire deterministic arithmetic chain (daily
loss capacity, per-trade budget, per-family verdict/reasons/sizing) from its
own embedded inputs and rejecting any mismatch - mirroring
``StrategyPolicyResult``'s own exhaustive quality-violation re-derivation one
stage forward, since Stage 7's core logic is pure arithmetic, not semantic
judgment.

The embedded ``StrategyPolicyResult`` (and, through it, the whole Stage
5/6A/6B/6C chain), ``TradingCycleConfig``, ``AccountRiskSnapshot`` and
``candidate_inputs`` are all carried unchanged: no evidence, direction, or
candidate fact is ever copied out of them - every ``RiskFamilyResult``
back-references its family only.

``RiskFamilyVerdict.ELIGIBLE_FOR_PORTFOLIO_REVIEW`` means only that this
family's account-risk ceiling permits it to proceed to Stage 8 review -
never that a trade, position, or execution of any kind has been approved.
``RiskFamilyResult.max_individual_risk`` means "the maximum risk this
candidate could consume if it were the only candidate considered against
this exact ``AccountRiskSnapshot``" - it is never "risk jointly reserved or
guaranteed available for this candidate." Multiple family results may each
expose an independent ceiling against the same account snapshot; Stage 7
makes no joint-allocation guarantee across simultaneously-eligible families.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Self

from pydantic import Field, model_validator

from app.core.config.trading_cycle import TradingCycleConfig
from app.core.enums.policy_gate import PolicyFamilyVerdict
from app.core.enums.risk_gate import RiskBlockReason, RiskFamilyVerdict, RiskGateOutcome
from app.core.enums.strategy_router import StrategyFamily
from app.core.models.base import DomainModel, Timestamp
from app.core.models.policy_gate_result import StrategyPolicyResult

_REASON_ORDER: tuple[RiskBlockReason, ...] = tuple(RiskBlockReason)


def _account_risk_state(
    account_snapshot: "AccountRiskSnapshot", trading_cycle_config: TradingCycleConfig
) -> tuple[Decimal, Decimal, Decimal]:
    """Independently re-derive the account-level risk-capacity figures - a
    locally-owned copy, not imported from ``app.risk.engine`` (whose own
    engine independently re-derives the identical arithmetic to produce its
    output), mirroring the Stage 5A/6A/6C precedent of the operational
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


def _expected_candidate_result(
    risk_per_unit: Decimal,
    remaining_daily_loss_capacity: Decimal,
    available_new_trade_risk: Decimal,
    per_trade_risk_budget: Decimal,
) -> tuple[RiskFamilyVerdict, tuple[RiskBlockReason, ...], Decimal | None, Decimal | None]:
    reason_set: set[RiskBlockReason] = set()
    if risk_per_unit <= 0:
        reason_set.add(RiskBlockReason.ZERO_OR_NEGATIVE_RISK_PER_UNIT)
    if remaining_daily_loss_capacity <= 0:
        reason_set.add(RiskBlockReason.DAILY_LOSS_LIMIT_REACHED)
    elif available_new_trade_risk <= 0:
        reason_set.add(RiskBlockReason.INSUFFICIENT_REMAINING_RISK_BUDGET)

    reasons = tuple(reason for reason in _REASON_ORDER if reason in reason_set)
    if reasons:
        return RiskFamilyVerdict.BLOCKED_BY_RISK, reasons, None, None

    max_individual_risk = min(per_trade_risk_budget, available_new_trade_risk)
    recommended_units = max_individual_risk / risk_per_unit
    return RiskFamilyVerdict.ELIGIBLE_FOR_PORTFOLIO_REVIEW, (), max_individual_risk, recommended_units


class AccountRiskSnapshot(DomainModel):
    """Explicit, caller-supplied point-in-time account-risk state.

    ``current_open_risk_to_stop`` is the maximum ADDITIONAL monetary loss
    from the current marks of already-open positions to their protective
    stops - never full entry-to-stop loss (that would double-count the
    entry-to-current segment already reflected in ``floating_pnl``). A
    position whose stop already guarantees profit relative to its current
    mark contributes zero, never a negative amount - definitionally
    non-negative, enforced at the field level. Stage 7 never enumerates
    individual positions; this is a single pre-aggregated fact.

    ``current_equity`` is not read by any Stage 7 V1 formula - carried for
    auditability and forward-compatibility with a future Max Drawdown Guard.
    """

    as_of: Timestamp
    rollover_equity: Annotated[Decimal, Field(gt=0)]
    current_equity: Annotated[Decimal, Field(gt=0)]
    realized_daily_pnl: Decimal
    floating_pnl: Decimal
    current_open_risk_to_stop: Annotated[Decimal, Field(ge=0)]


class CandidateRiskInput(DomainModel):
    """The one external sizing fact Stage 7 cannot derive itself.

    ``risk_per_unit`` is an opaque, deterministic, caller-supplied fact: the
    monetary additional loss for one generic candidate unit if its
    protective risk boundary is reached. Deliberately unconstrained at the
    field level (no ``gt=0``) so a non-positive value remains representable
    as the normal business-rule block ``ZERO_OR_NEGATIVE_RISK_PER_UNIT``
    rather than a caller/model-construction error.
    """

    family: StrategyFamily
    risk_per_unit: Decimal


class RiskFamilyResult(DomainModel):
    """One Policy-family's Stage 7 account-risk verdict.

    ``reasons`` is empty if and only if ``verdict`` is
    ``ELIGIBLE_FOR_PORTFOLIO_REVIEW``; when non-empty it is canonically
    ordered (``RiskBlockReason`` declaration order) and duplicate-free.
    ``POLICY_NOT_ELIGIBLE`` is always the sole reason when present.
    ``DAILY_LOSS_LIMIT_REACHED`` and ``INSUFFICIENT_REMAINING_RISK_BUDGET``
    are mutually exclusive; ``ZERO_OR_NEGATIVE_RISK_PER_UNIT`` may coexist
    with either. Carries no direction, ``risk_per_unit``, Policy/Judge
    payload, or market evidence - all remain recoverable only through the
    embedded inputs on ``StrategyRiskResult``.
    """

    family: StrategyFamily
    verdict: RiskFamilyVerdict
    reasons: tuple[RiskBlockReason, ...] = ()
    max_individual_risk: Decimal | None = None
    recommended_units: Decimal | None = None

    @model_validator(mode="after")
    def _validate_verdict_matches_reasons(self) -> Self:
        expected = RiskFamilyVerdict.BLOCKED_BY_RISK if self.reasons else RiskFamilyVerdict.ELIGIBLE_FOR_PORTFOLIO_REVIEW
        if self.verdict is not expected:
            raise ValueError("verdict must be BLOCKED_BY_RISK iff reasons is non-empty")
        return self

    @model_validator(mode="after")
    def _validate_reasons_canonical_and_unique(self) -> Self:
        indexes = [_REASON_ORDER.index(reason) for reason in self.reasons]
        if indexes != sorted(indexes):
            raise ValueError("reasons must be in canonical RiskBlockReason order")
        if len(set(indexes)) != len(indexes):
            raise ValueError("reasons must not contain duplicates")
        return self

    @model_validator(mode="after")
    def _validate_policy_not_eligible_exclusive(self) -> Self:
        if RiskBlockReason.POLICY_NOT_ELIGIBLE in self.reasons and self.reasons != (RiskBlockReason.POLICY_NOT_ELIGIBLE,):
            raise ValueError("POLICY_NOT_ELIGIBLE must be the only reason when present")
        return self

    @model_validator(mode="after")
    def _validate_daily_and_insufficient_mutually_exclusive(self) -> Self:
        if (
            RiskBlockReason.DAILY_LOSS_LIMIT_REACHED in self.reasons
            and RiskBlockReason.INSUFFICIENT_REMAINING_RISK_BUDGET in self.reasons
        ):
            raise ValueError("DAILY_LOSS_LIMIT_REACHED and INSUFFICIENT_REMAINING_RISK_BUDGET are mutually exclusive")
        return self

    @model_validator(mode="after")
    def _validate_sizing_fields(self) -> Self:
        if self.verdict is RiskFamilyVerdict.ELIGIBLE_FOR_PORTFOLIO_REVIEW:
            if self.max_individual_risk is None or self.max_individual_risk <= 0:
                raise ValueError("ELIGIBLE_FOR_PORTFOLIO_REVIEW requires max_individual_risk > 0")
            if self.recommended_units is None or self.recommended_units <= 0:
                raise ValueError("ELIGIBLE_FOR_PORTFOLIO_REVIEW requires recommended_units > 0")
        else:
            if self.max_individual_risk is not None:
                raise ValueError("BLOCKED_BY_RISK must not carry max_individual_risk")
            if self.recommended_units is not None:
                raise ValueError("BLOCKED_BY_RISK must not carry recommended_units")
        return self


class StrategyRiskResult(DomainModel):
    """Deterministic Stage 7 aggregation: one account-risk verdict per
    ``StrategyPolicyResult.family_results`` entry, plus the
    participation-derived top-level outcome.

    Every family result is independently derived from the *same* embedded
    ``account_snapshot``/``trading_cycle_config`` - no budget is reserved,
    subtracted, or sequenced between family results. Multiple simultaneously
    ``ELIGIBLE_FOR_PORTFOLIO_REVIEW`` families are not guaranteed jointly
    deployable; see ``RiskFamilyResult.max_individual_risk``.
    """

    strategy_policy_result: StrategyPolicyResult
    trading_cycle_config: TradingCycleConfig
    account_snapshot: AccountRiskSnapshot
    candidate_inputs: tuple[CandidateRiskInput, ...]
    outcome: RiskGateOutcome
    family_results: tuple[RiskFamilyResult, ...]

    @model_validator(mode="after")
    def _validate_family_results_match_policy_family_results(self) -> Self:
        expected = tuple(result.family for result in self.strategy_policy_result.family_results)
        actual = tuple(result.family for result in self.family_results)
        if actual != expected:
            raise ValueError("family_results must cover exactly strategy_policy_result.family_results, in the same order")
        return self

    @model_validator(mode="after")
    def _validate_candidate_inputs_no_duplicates(self) -> Self:
        families = [candidate.family for candidate in self.candidate_inputs]
        if len(set(families)) != len(families):
            raise ValueError("candidate_inputs must not contain duplicate families")
        return self

    @model_validator(mode="after")
    def _validate_candidate_inputs_match_eligible_families(self) -> Self:
        eligible_families = {
            result.family
            for result in self.strategy_policy_result.family_results
            if result.verdict is PolicyFamilyVerdict.ELIGIBLE_FOR_RISK_REVIEW
        }
        candidate_families = {candidate.family for candidate in self.candidate_inputs}
        if candidate_families != eligible_families:
            raise ValueError("candidate_inputs must cover exactly the Policy-eligible families, no more, no fewer")
        return self

    @model_validator(mode="after")
    def _validate_outcome(self) -> Self:
        any_eligible = any(result.verdict is RiskFamilyVerdict.ELIGIBLE_FOR_PORTFOLIO_REVIEW for result in self.family_results)
        expected = RiskGateOutcome.SOME_ELIGIBLE_FOR_PORTFOLIO_REVIEW if any_eligible else RiskGateOutcome.NO_RISK_ELIGIBLE_FAMILY
        if self.outcome is not expected:
            raise ValueError(f"outcome {self.outcome} does not match per-family-derived outcome {expected}")
        return self

    @model_validator(mode="after")
    def _validate_family_verdicts(self) -> Self:
        candidate_by_family = {candidate.family: candidate for candidate in self.candidate_inputs}
        remaining_daily_loss_capacity, available_new_trade_risk, per_trade_risk_budget = _account_risk_state(
            self.account_snapshot, self.trading_cycle_config
        )

        for policy_result, risk_result in zip(self.strategy_policy_result.family_results, self.family_results, strict=True):
            if policy_result.verdict is PolicyFamilyVerdict.BLOCKED:
                if risk_result.verdict is not RiskFamilyVerdict.BLOCKED_BY_RISK:
                    raise ValueError(f"family {risk_result.family}: Policy-BLOCKED family must be BLOCKED_BY_RISK")
                if risk_result.reasons != (RiskBlockReason.POLICY_NOT_ELIGIBLE,):
                    raise ValueError(f"family {risk_result.family}: Policy-BLOCKED family must carry exactly (POLICY_NOT_ELIGIBLE,)")
                continue

            candidate = candidate_by_family.get(risk_result.family)
            if candidate is None:
                raise ValueError(f"family {risk_result.family}: missing CandidateRiskInput for a Policy-eligible family")

            expected_verdict, expected_reasons, expected_max_individual_risk, expected_recommended_units = _expected_candidate_result(
                candidate.risk_per_unit, remaining_daily_loss_capacity, available_new_trade_risk, per_trade_risk_budget
            )
            if risk_result.verdict is not expected_verdict:
                raise ValueError(f"family {risk_result.family}: verdict does not match expected risk evaluation")
            if risk_result.reasons != expected_reasons:
                raise ValueError(f"family {risk_result.family}: reasons do not match expected risk evaluation")
            if risk_result.max_individual_risk != expected_max_individual_risk:
                raise ValueError(f"family {risk_result.family}: max_individual_risk does not match expected risk evaluation")
            if risk_result.recommended_units != expected_recommended_units:
                raise ValueError(f"family {risk_result.family}: recommended_units does not match expected risk evaluation")
        return self


__all__ = ["AccountRiskSnapshot", "CandidateRiskInput", "RiskFamilyResult", "StrategyRiskResult"]
