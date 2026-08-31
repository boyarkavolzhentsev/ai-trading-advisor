"""Stage 9 deterministic Session Gate output contract.

Aggregates one already-produced ``StrategyPortfolioResult`` plus one explicit
``locked_override`` into a per-family session verdict: whether that family's
Stage 8 portfolio allocation may proceed to Stage 10 runtime review under the
current, deterministically-derived ``TradingSessionStatus``. This model
validates structural consistency only by independently re-deriving the
entire deterministic session-status/precedence logic (rollover-based session
target, Stage 7's own daily-loss-capacity formula, the ``locked_override``
kill-switch, and their fixed precedence) from its own embedded input and
rejecting any mismatch - mirroring every prior stage's own exhaustive
re-derivation one stage forward, since Stage 9's core gating logic is pure
arithmetic/precedence, not semantic judgment.

The embedded ``StrategyPortfolioResult`` (and, through it, the whole Stage
5/6/7/8 chain) is carried unchanged: no evidence, direction, account state,
or candidate fact is ever copied out of it - every ``SessionFamilyResult``
back-references its family only. ``locked_override`` is the one genuinely
new caller-supplied fact Stage 9 needs (nothing upstream can express an
explicit operator/runtime kill-switch); it is retained verbatim so
``session_status`` remains independently re-derivable, mirroring
``StrategyRiskResult.candidate_inputs`` - the same precedent for retaining a
caller-supplied fact that has no upstream source.

``SessionFamilyVerdict.ELIGIBLE_FOR_RUNTIME_REVIEW`` means only that this
family's portfolio allocation is untouched by any session-level block and
may proceed to Stage 10 runtime review - never that a trade, position, or
execution of any kind has been approved. Stage 9 V1 is a strict pass/block
gate: an eligible family's ``session_allocated_risk`` is always an exact,
unscaled copy of its upstream ``portfolio_allocated_risk`` - Stage 9 V1 has
no approved risk-reduction formula and therefore never rescales it.
``TradingSessionStatus.CAPITAL_PRESERVATION`` and ``.REDUCED_RISK`` are
deferred: no Stage 9 V1 formula can ever produce them, and this model
rejects them outright.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Self

from pydantic import model_validator

from app.core.enums.portfolio import PortfolioFamilyVerdict
from app.core.enums.session import TradingSessionStatus
from app.core.enums.session_gate import SessionBlockReason, SessionFamilyVerdict, SessionGateOutcome
from app.core.enums.strategy_router import StrategyFamily
from app.core.models.base import DomainModel
from app.core.models.portfolio_result import PortfolioFamilyResult, StrategyPortfolioResult

_V1_REACHABLE_STATUSES: frozenset[TradingSessionStatus] = frozenset(
    {
        TradingSessionStatus.ACTIVE,
        TradingSessionStatus.LOSS_LIMIT_REACHED,
        TradingSessionStatus.TARGET_REACHED,
        TradingSessionStatus.LOCKED,
    }
)
"""Stage 9 V1's entire codomain. ``CAPITAL_PRESERVATION`` and
``REDUCED_RISK`` are declared on ``TradingSessionStatus`` for forward
compatibility but are never reachable in V1 - no approved trigger/threshold
exists for either (see the approved Stage 9 design)."""

_SESSION_REASON_BY_STATUS: dict[TradingSessionStatus, SessionBlockReason] = {
    TradingSessionStatus.LOCKED: SessionBlockReason.SESSION_LOCKED,
    TradingSessionStatus.LOSS_LIMIT_REACHED: SessionBlockReason.LOSS_LIMIT_REACHED,
    TradingSessionStatus.TARGET_REACHED: SessionBlockReason.TARGET_REACHED,
}


def _derive_session_status(
    strategy_portfolio_result: StrategyPortfolioResult, locked_override: bool
) -> TradingSessionStatus:
    """Independently re-derive the Stage 9 session status - a locally-owned
    copy, not imported from ``app.statistics.session`` (whose own gate
    independently re-derives the identical precedence to produce its
    output), mirroring the Stage 5A/6A/6C/7/8 precedent of the operational
    component and the result model's self-validation maintaining
    independent copies of the same primitive rather than cross-importing one
    from the other."""
    if locked_override:
        return TradingSessionStatus.LOCKED

    account_snapshot = strategy_portfolio_result.strategy_risk_result.account_snapshot
    trading_cycle_config = strategy_portfolio_result.strategy_risk_result.trading_cycle_config

    daily_loss_limit = account_snapshot.rollover_equity * (trading_cycle_config.daily_risk_limit_percent / Decimal("100"))
    current_daily_pnl = account_snapshot.realized_daily_pnl + account_snapshot.floating_pnl
    loss_consumed = max(Decimal("0"), -current_daily_pnl)
    remaining_daily_loss_capacity = max(Decimal("0"), daily_loss_limit - loss_consumed)
    if remaining_daily_loss_capacity <= 0:
        return TradingSessionStatus.LOSS_LIMIT_REACHED

    target_profit_amount = account_snapshot.rollover_equity * (trading_cycle_config.target_profit_percent / Decimal("100"))
    current_session_pnl = account_snapshot.current_equity - account_snapshot.rollover_equity
    if current_session_pnl >= target_profit_amount:
        return TradingSessionStatus.TARGET_REACHED

    return TradingSessionStatus.ACTIVE


def _expected_family_result(
    portfolio_result: PortfolioFamilyResult, session_status: TradingSessionStatus
) -> tuple[SessionFamilyVerdict, tuple[SessionBlockReason, ...], Decimal | None]:
    if portfolio_result.verdict is PortfolioFamilyVerdict.BLOCKED_BY_PORTFOLIO:
        return SessionFamilyVerdict.BLOCKED_BY_SESSION, (SessionBlockReason.PORTFOLIO_NOT_ELIGIBLE,), None

    if session_status is TradingSessionStatus.ACTIVE:
        return SessionFamilyVerdict.ELIGIBLE_FOR_RUNTIME_REVIEW, (), portfolio_result.portfolio_allocated_risk

    return SessionFamilyVerdict.BLOCKED_BY_SESSION, (_SESSION_REASON_BY_STATUS[session_status],), None


class SessionFamilyResult(DomainModel):
    """One Portfolio-family's Stage 9 session verdict.

    ``reasons`` is empty if and only if ``verdict`` is
    ``ELIGIBLE_FOR_RUNTIME_REVIEW``; when non-empty it carries exactly one
    canonical reason. Carries no direction, allocation formula, account
    snapshot, config, or upstream evidence - all remain recoverable only
    through the embedded ``StrategyPortfolioResult`` on
    ``StrategySessionResult``.
    """

    family: StrategyFamily
    verdict: SessionFamilyVerdict
    reasons: tuple[SessionBlockReason, ...] = ()
    session_allocated_risk: Decimal | None = None

    @model_validator(mode="after")
    def _validate_verdict_matches_reasons(self) -> Self:
        expected = SessionFamilyVerdict.BLOCKED_BY_SESSION if self.reasons else SessionFamilyVerdict.ELIGIBLE_FOR_RUNTIME_REVIEW
        if self.verdict is not expected:
            raise ValueError("verdict must be BLOCKED_BY_SESSION iff reasons is non-empty")
        return self

    @model_validator(mode="after")
    def _validate_reasons_shape(self) -> Self:
        if len(self.reasons) > 1:
            raise ValueError("reasons must carry at most one canonical reason")
        return self

    @model_validator(mode="after")
    def _validate_sizing_fields(self) -> Self:
        if self.verdict is SessionFamilyVerdict.ELIGIBLE_FOR_RUNTIME_REVIEW:
            if self.session_allocated_risk is None or self.session_allocated_risk <= 0:
                raise ValueError("ELIGIBLE_FOR_RUNTIME_REVIEW requires session_allocated_risk > 0")
        else:
            if self.session_allocated_risk is not None:
                raise ValueError("BLOCKED_BY_SESSION must not carry session_allocated_risk")
        return self


class StrategySessionResult(DomainModel):
    """Deterministic Stage 9 aggregation: one session verdict per
    ``StrategyPortfolioResult.family_results`` entry, plus the
    participation-derived top-level outcome.

    Session state (``session_status``) is computed once, globally, from the
    embedded ``account_snapshot``/``trading_cycle_config`` and
    ``locked_override`` - never per family - and applied identically to
    every otherwise-eligible family. A Stage-8-blocked family can never
    become session-eligible, regardless of ``session_status``.
    """

    strategy_portfolio_result: StrategyPortfolioResult
    locked_override: bool = False
    session_status: TradingSessionStatus
    outcome: SessionGateOutcome
    family_results: tuple[SessionFamilyResult, ...]

    @model_validator(mode="after")
    def _validate_family_results_match_portfolio_family_results(self) -> Self:
        expected = tuple(result.family for result in self.strategy_portfolio_result.family_results)
        actual = tuple(result.family for result in self.family_results)
        if actual != expected:
            raise ValueError("family_results must cover exactly strategy_portfolio_result.family_results, in the same order")
        return self

    @model_validator(mode="after")
    def _validate_session_status_reachable(self) -> Self:
        if self.session_status not in _V1_REACHABLE_STATUSES:
            raise ValueError(f"session_status {self.session_status} is not reachable in Stage 9 V1")
        return self

    @model_validator(mode="after")
    def _validate_session_status_matches_expected(self) -> Self:
        expected_status = _derive_session_status(self.strategy_portfolio_result, self.locked_override)
        if self.session_status is not expected_status:
            raise ValueError(f"session_status {self.session_status} does not match expected {expected_status}")
        return self

    @model_validator(mode="after")
    def _validate_outcome(self) -> Self:
        any_eligible = any(result.verdict is SessionFamilyVerdict.ELIGIBLE_FOR_RUNTIME_REVIEW for result in self.family_results)
        expected = (
            SessionGateOutcome.SOME_ELIGIBLE_FOR_RUNTIME_REVIEW if any_eligible else SessionGateOutcome.NO_SESSION_ELIGIBLE_FAMILY
        )
        if self.outcome is not expected:
            raise ValueError(f"outcome {self.outcome} does not match per-family-derived outcome {expected}")
        return self

    @model_validator(mode="after")
    def _validate_family_verdicts_match_expected_result(self) -> Self:
        for portfolio_result, session_result in zip(
            self.strategy_portfolio_result.family_results, self.family_results, strict=True
        ):
            expected_verdict, expected_reasons, expected_allocation = _expected_family_result(
                portfolio_result, self.session_status
            )
            if session_result.verdict is not expected_verdict:
                raise ValueError(f"family {session_result.family}: verdict does not match expected session evaluation")
            if session_result.reasons != expected_reasons:
                raise ValueError(f"family {session_result.family}: reasons do not match expected session evaluation")
            if session_result.session_allocated_risk != expected_allocation:
                raise ValueError(f"family {session_result.family}: session_allocated_risk does not match expected session evaluation")
        return self


__all__ = ["SessionFamilyResult", "StrategySessionResult"]
