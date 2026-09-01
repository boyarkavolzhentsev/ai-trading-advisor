"""Stage 8 deterministic Portfolio/Diversification output contract.

Aggregates one already-produced ``StrategyRiskResult`` into a per-family
portfolio verdict: whether that family's independent Stage 7 risk ceiling
(``max_individual_risk``) may proceed to Stage 9 session review, jointly
against every other simultaneously Risk-eligible family sharing the same
evaluation's single symbol. This model validates structural consistency only
by independently re-deriving the entire deterministic arithmetic chain
(portfolio risk budget, remaining capacity, group-wide scaling regime,
per-family verdict/reasons/allocation) from its own embedded input and
rejecting any mismatch - mirroring ``StrategyRiskResult``'s own exhaustive
re-derivation one stage forward, since Stage 8's core logic is pure
arithmetic, not semantic judgment.

Unlike every prior Decision-layer stage, Stage 8's per-family results are
genuinely group-dependent: each family's ``portfolio_allocated_risk`` can
depend on every other simultaneously-eligible family's own
``max_individual_risk`` (via the shared proportional-scaling factor). This is
a deliberate, necessary departure from the "each family judged in complete
isolation" discipline every earlier stage enforced (see
``app.judge.judge``'s own no-cross-family-voting precedent) - Stage 8 exists
specifically to reason about multiple candidates jointly from a portfolio
allocation perspective (see the approved Stage 8 design), while still never
introducing ranking, preference, or market-semantic weighting: every
eligible family receives the identical scaling factor, so no family is ever
favored over another.

The embedded ``StrategyRiskResult`` (and, through it, the whole Stage
5/6/7 chain) is carried unchanged: no evidence, direction, account state, or
candidate fact is ever copied out of it - every ``PortfolioFamilyResult``
back-references its family only. No ``PortfolioExposureSnapshot`` or
``CandidatePortfolioInput`` exists: the only account facts Stage 8 V1 needs
(``current_equity``, ``current_open_risk_to_stop``) are already present on
the embedded ``strategy_risk_result.account_snapshot``, and the only config
fact needed (``portfolio_risk_limit_percent``) is already present on the
embedded ``strategy_risk_result.trading_cycle_config`` - reusing them avoids
both a redundant caller-supplied fact and the cross-object consistency
problem a second snapshot would create.

``PortfolioFamilyVerdict.ELIGIBLE_FOR_SESSION_REVIEW`` means only that this
family's risk-to-stop allocation fits within the account's portfolio-risk
budget and may proceed to Stage 9 session review - never that a trade,
position, or execution of any kind has been approved. Stage 8 never inspects
direction: opposite-direction, same-symbol families are treated identically
to same-direction ones, both counting fully toward the shared capacity, with
no netting or offsetting of any kind.

Stage 8 jointly enforces two independent shared capacities against the sum
of every simultaneously Risk-eligible family's ``max_individual_risk``:
Stage 7's daily-loss-derived ``available_new_trade_risk`` (re-derived
locally below - never imported from ``app.risk``) and Stage 8's own
``portfolio_risk_limit_percent``-derived capacity. ``joint_new_risk_capacity``
is the minimum of the two, so the sum of every family's
``portfolio_allocated_risk`` can never exceed either capacity individually -
correcting a gap where enforcing the portfolio-percent capacity alone could
jointly allocate aggregate new risk above Stage 7's shared daily-loss
capacity even though every individual Stage 7 family verdict was
independently valid.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Self

from pydantic import model_validator

from app.core.enums.portfolio import PortfolioBlockReason, PortfolioFamilyVerdict, PortfolioGateOutcome
from app.core.enums.risk_gate import RiskFamilyVerdict
from app.core.enums.strategy_router import StrategyFamily
from app.core.models.base import DomainModel
from app.core.models.risk_gate_result import AccountRiskSnapshot, RiskFamilyResult, StrategyRiskResult
from app.core.config.trading_cycle import TradingCycleConfig

_ExpectedFamilyResult = tuple[PortfolioFamilyVerdict, tuple[PortfolioBlockReason, ...], Decimal | None]


def _stage7_shared_capacity(account_snapshot: AccountRiskSnapshot, trading_cycle_config: TradingCycleConfig) -> Decimal:
    """Independently re-derive Stage 7's shared daily new-trade-risk
    capacity - a locally-owned copy, not imported from ``app.risk.engine`` or
    ``app.diversification.supervisor`` (each of which already maintains its
    own independent copy of this identical formula), mirroring the Stage
    5A/6A/6C/7 precedent of the operational component and the result model's
    self-validation maintaining independent copies of the same primitive
    rather than cross-importing one from the other."""
    daily_loss_limit = account_snapshot.rollover_equity * (trading_cycle_config.daily_risk_limit_percent / Decimal("100"))
    current_daily_pnl = account_snapshot.realized_daily_pnl + account_snapshot.floating_pnl
    loss_consumed = max(Decimal("0"), -current_daily_pnl)
    remaining_daily_loss_capacity = max(Decimal("0"), daily_loss_limit - loss_consumed)
    return max(Decimal("0"), remaining_daily_loss_capacity - account_snapshot.current_open_risk_to_stop)


def _remaining_portfolio_capacity(strategy_risk_result: StrategyRiskResult) -> Decimal:
    """Independently re-derive the portfolio-level risk capacity - a
    locally-owned copy, not imported from ``app.diversification.supervisor``
    (whose own engine independently re-derives the identical figure to
    produce its output), mirroring the Stage 5A/6A/6C/7 precedent of the
    operational component and the result model's self-validation
    maintaining independent copies of the same primitive rather than
    cross-importing one from the other."""
    account_snapshot = strategy_risk_result.account_snapshot
    trading_cycle_config = strategy_risk_result.trading_cycle_config
    portfolio_risk_budget = account_snapshot.current_equity * (trading_cycle_config.portfolio_risk_limit_percent / Decimal("100"))
    return max(Decimal("0"), portfolio_risk_budget - account_snapshot.current_open_risk_to_stop)


def _joint_new_risk_capacity(strategy_risk_result: StrategyRiskResult) -> tuple[Decimal, Decimal, Decimal]:
    stage7_shared_capacity = _stage7_shared_capacity(strategy_risk_result.account_snapshot, strategy_risk_result.trading_cycle_config)
    stage8_portfolio_capacity = _remaining_portfolio_capacity(strategy_risk_result)
    return stage7_shared_capacity, stage8_portfolio_capacity, min(stage7_shared_capacity, stage8_portfolio_capacity)


def _expected_group_results(strategy_risk_result: StrategyRiskResult) -> dict[StrategyFamily, _ExpectedFamilyResult]:
    stage7_shared_capacity, stage8_portfolio_capacity, joint_new_risk_capacity = _joint_new_risk_capacity(strategy_risk_result)
    eligible_results = [
        result for result in strategy_risk_result.family_results if result.verdict is RiskFamilyVerdict.ELIGIBLE_FOR_PORTFOLIO_REVIEW
    ]
    total_requested = sum((result.max_individual_risk for result in eligible_results), Decimal("0"))

    expected: dict[StrategyFamily, _ExpectedFamilyResult] = {}
    for risk_result in strategy_risk_result.family_results:
        if risk_result.verdict is RiskFamilyVerdict.BLOCKED_BY_RISK:
            expected[risk_result.family] = (
                PortfolioFamilyVerdict.BLOCKED_BY_PORTFOLIO,
                (PortfolioBlockReason.RISK_NOT_ELIGIBLE,),
                None,
            )
        elif stage7_shared_capacity <= 0:
            expected[risk_result.family] = (
                PortfolioFamilyVerdict.BLOCKED_BY_PORTFOLIO,
                (PortfolioBlockReason.DAILY_RISK_CAPACITY_EXHAUSTED,),
                None,
            )
        elif stage8_portfolio_capacity <= 0:
            expected[risk_result.family] = (
                PortfolioFamilyVerdict.BLOCKED_BY_PORTFOLIO,
                (PortfolioBlockReason.GLOBAL_PORTFOLIO_CAP_REACHED,),
                None,
            )
        elif total_requested <= joint_new_risk_capacity:
            expected[risk_result.family] = (PortfolioFamilyVerdict.ELIGIBLE_FOR_SESSION_REVIEW, (), risk_result.max_individual_risk)
        else:
            scaling_factor = joint_new_risk_capacity / total_requested
            expected[risk_result.family] = (
                PortfolioFamilyVerdict.ELIGIBLE_FOR_SESSION_REVIEW,
                (),
                risk_result.max_individual_risk * scaling_factor,
            )
    return expected


class PortfolioFamilyResult(DomainModel):
    """One Risk-family's Stage 8 portfolio verdict.

    ``reasons`` is empty if and only if ``verdict`` is
    ``ELIGIBLE_FOR_SESSION_REVIEW``; when non-empty it carries exactly one
    canonical reason - ``RISK_NOT_ELIGIBLE``, ``DAILY_RISK_CAPACITY_EXHAUSTED``
    and ``GLOBAL_PORTFOLIO_CAP_REACHED`` are structurally mutually exclusive
    (the first only ever applies to a Risk-blocked family, which never
    reaches the joint-capacity check the other two represent;
    ``DAILY_RISK_CAPACITY_EXHAUSTED`` takes precedence over
    ``GLOBAL_PORTFOLIO_CAP_REACHED`` whenever both shared capacities are
    simultaneously non-positive). Carries no direction, ``risk_per_unit``,
    account snapshot, config, or upstream evidence - all remain recoverable
    only through the embedded ``StrategyRiskResult`` on
    ``StrategyPortfolioResult``.
    """

    family: StrategyFamily
    verdict: PortfolioFamilyVerdict
    reasons: tuple[PortfolioBlockReason, ...] = ()
    portfolio_allocated_risk: Decimal | None = None

    @model_validator(mode="after")
    def _validate_verdict_matches_reasons(self) -> Self:
        expected = PortfolioFamilyVerdict.BLOCKED_BY_PORTFOLIO if self.reasons else PortfolioFamilyVerdict.ELIGIBLE_FOR_SESSION_REVIEW
        if self.verdict is not expected:
            raise ValueError("verdict must be BLOCKED_BY_PORTFOLIO iff reasons is non-empty")
        return self

    @model_validator(mode="after")
    def _validate_reasons_shape(self) -> Self:
        if len(self.reasons) > 1:
            raise ValueError("reasons must carry at most one canonical reason")
        return self

    @model_validator(mode="after")
    def _validate_sizing_fields(self) -> Self:
        if self.verdict is PortfolioFamilyVerdict.ELIGIBLE_FOR_SESSION_REVIEW:
            if self.portfolio_allocated_risk is None or self.portfolio_allocated_risk <= 0:
                raise ValueError("ELIGIBLE_FOR_SESSION_REVIEW requires portfolio_allocated_risk > 0")
        else:
            if self.portfolio_allocated_risk is not None:
                raise ValueError("BLOCKED_BY_PORTFOLIO must not carry portfolio_allocated_risk")
        return self


class StrategyPortfolioResult(DomainModel):
    """Deterministic Stage 8 aggregation: one portfolio verdict per
    ``StrategyRiskResult.family_results`` entry, plus the
    participation-derived top-level outcome.

    Every simultaneously Risk-eligible family result is jointly derived from
    the *same* embedded ``account_snapshot``/``trading_cycle_config`` via an
    identical proportional-scaling factor - no budget is reserved,
    sequenced, or preferentially assigned between family results, and no
    family's direction ever influences another's (or its own) allocation.
    """

    strategy_risk_result: StrategyRiskResult
    outcome: PortfolioGateOutcome
    family_results: tuple[PortfolioFamilyResult, ...]

    @model_validator(mode="after")
    def _validate_family_results_match_risk_family_results(self) -> Self:
        expected = tuple(result.family for result in self.strategy_risk_result.family_results)
        actual = tuple(result.family for result in self.family_results)
        if actual != expected:
            raise ValueError("family_results must cover exactly strategy_risk_result.family_results, in the same order")
        return self

    @model_validator(mode="after")
    def _validate_outcome(self) -> Self:
        any_eligible = any(result.verdict is PortfolioFamilyVerdict.ELIGIBLE_FOR_SESSION_REVIEW for result in self.family_results)
        expected = (
            PortfolioGateOutcome.SOME_ELIGIBLE_FOR_SESSION_REVIEW if any_eligible else PortfolioGateOutcome.NO_PORTFOLIO_ELIGIBLE_FAMILY
        )
        if self.outcome is not expected:
            raise ValueError(f"outcome {self.outcome} does not match per-family-derived outcome {expected}")
        return self

    @model_validator(mode="after")
    def _validate_family_verdicts_match_expected_group_result(self) -> Self:
        expected_by_family = _expected_group_results(self.strategy_risk_result)
        for family_result in self.family_results:
            expected_verdict, expected_reasons, expected_allocation = expected_by_family[family_result.family]
            if family_result.verdict is not expected_verdict:
                raise ValueError(f"family {family_result.family}: verdict does not match expected portfolio evaluation")
            if family_result.reasons != expected_reasons:
                raise ValueError(f"family {family_result.family}: reasons do not match expected portfolio evaluation")
            if family_result.portfolio_allocated_risk != expected_allocation:
                raise ValueError(f"family {family_result.family}: portfolio_allocated_risk does not match expected portfolio evaluation")
        return self

    @model_validator(mode="after")
    def _validate_allocation_never_exceeds_max_individual_risk(self) -> Self:
        risk_by_family: dict[StrategyFamily, RiskFamilyResult] = {
            result.family: result for result in self.strategy_risk_result.family_results
        }
        for family_result in self.family_results:
            if family_result.portfolio_allocated_risk is None:
                continue
            max_individual_risk = risk_by_family[family_result.family].max_individual_risk
            if max_individual_risk is None or family_result.portfolio_allocated_risk > max_individual_risk:
                raise ValueError(f"family {family_result.family}: portfolio_allocated_risk exceeds its Stage 7 max_individual_risk")
        return self

    @model_validator(mode="after")
    def _validate_total_allocation_within_remaining_capacity(self) -> Self:
        stage7_shared_capacity, stage8_portfolio_capacity, joint_new_risk_capacity = _joint_new_risk_capacity(self.strategy_risk_result)
        total_allocated = sum(
            (result.portfolio_allocated_risk for result in self.family_results if result.portfolio_allocated_risk is not None),
            Decimal("0"),
        )
        if total_allocated > stage7_shared_capacity:
            raise ValueError("sum of portfolio_allocated_risk exceeds stage7_shared_capacity")
        if total_allocated > stage8_portfolio_capacity:
            raise ValueError("sum of portfolio_allocated_risk exceeds stage8_portfolio_capacity")
        if total_allocated > joint_new_risk_capacity:
            raise ValueError("sum of portfolio_allocated_risk exceeds joint_new_risk_capacity")
        return self


__all__ = ["PortfolioFamilyResult", "StrategyPortfolioResult"]
