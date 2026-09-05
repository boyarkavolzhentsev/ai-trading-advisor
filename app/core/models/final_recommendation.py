"""Final Recommendation output contracts (Final Runtime Integration, Part D).

Converts one already-completed ``DecisionRiskPipelineResult`` into a per-
Session-eligible-``StrategyFamily`` broker-normalized, advisory-only
recommendation via existing Stage 10C ``compute_broker_sizing``. Deliberately
narrower than ``PositionRecord``/``MT5TrackedRecommendation`` (never reused
here - see the approved Final Recommendation design): carries no
``market: MarketType`` (that fact belongs only to the later Final
Recommendation -> Stage 10E wiring boundary, which this stage does not
build), no confidence, no ranking, no LLM-generated field of any kind.

The embedded ``DecisionRiskPipelineResult`` (and, through it, the whole Stage
5-9 chain) and each family's ``MT5BrokerSizingResult`` are carried unchanged:
no evidence, direction, account state, or sizing fact is ever copied out in
isolation - every ``FinalRecommendationFamilyResult`` back-references its
family only.

``FinalRecommendationVerdict.ACTIONABLE`` means only that a concrete,
broker-normalized advisory recommendation was constructed - never that a
trade, position, or execution of any kind has occurred or been approved.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Self

from pydantic import Field, model_validator

from app.core.enums.decision_risk_pipeline import DecisionRiskPipelineOutcome
from app.core.enums.final_recommendation import (
    FinalRecommendationBlockReason,
    FinalRecommendationOutcome,
    FinalRecommendationVerdict,
)
from app.core.enums.mt5_sizing import MT5SizingOutcome
from app.core.enums.strategy_router import StrategyFamily
from app.core.enums.trade import TradeDirection
from app.core.models.base import DomainModel, Price, Symbol, Timestamp
from app.core.models.decision_risk_pipeline import DecisionRiskPipelineResult
from app.core.models.mt5_sizing import MT5BrokerSizingResult

_NO_SIZING_ATTEMPT_REASONS: frozenset[FinalRecommendationBlockReason] = frozenset(
    {
        FinalRecommendationBlockReason.SESSION_NOT_ELIGIBLE,
        FinalRecommendationBlockReason.SYMBOL_FACTS_MISMATCH,
        FinalRecommendationBlockReason.SETUP_EXPIRED,
    }
)
"""The three ``FinalRecommendationBlockReason`` members that block a family
before Stage 10C is ever invoked for it - the only reasons under which
``FinalRecommendationFamilyResult.sizing_result`` is absent."""


class FinalRecommendation(DomainModel):
    """One Session-eligible family's concrete, broker-normalized advisory
    recommendation.

    Every field is an unchanged copy of an already-produced upstream fact
    (``CandidateTradeSetup``, ``MT5BrokerSizingResult``, or a caller-supplied
    fact) - no value is re-derived. ``account_currency`` labels
    ``approved_risk_amount`` with the exact, unchanged, broker-reported
    ``MT5AccountFacts.currency`` value - never hardcoded, never converted.
    """

    trade_id: Annotated[str, Field(min_length=1)]
    family: StrategyFamily
    symbol: Symbol
    direction: TradeDirection
    entry_price: Price
    stop_loss: Price
    take_profit_levels: tuple[Price, ...] = ()
    approved_volume: Annotated[Decimal, Field(gt=0)]
    approved_risk_amount: Annotated[Decimal, Field(gt=0)]
    account_currency: Annotated[str, Field(min_length=1)]
    signal_time: Timestamp
    valid_until: Timestamp


class FinalRecommendationFamilyResult(DomainModel):
    """One Session-family's Final Recommendation verdict.

    ``reasons`` is empty if and only if ``verdict`` is ``ACTIONABLE``; when
    non-empty it carries exactly one reason - every check this stage performs
    is sequential/short-circuiting, mirroring ``PortfolioFamilyResult``/
    ``SessionFamilyResult``'s own "at most one reason" discipline.
    ``sizing_result`` is present if and only if a Stage 10C sizing attempt was
    actually made for this family (i.e. ``verdict`` is ``ACTIONABLE``, or
    ``reasons`` is ``(SIZING_NOT_ACTIONABLE,)``) - never fabricated for a
    family blocked before reaching Stage 10C.
    """

    family: StrategyFamily
    verdict: FinalRecommendationVerdict
    reasons: tuple[FinalRecommendationBlockReason, ...] = ()
    sizing_result: MT5BrokerSizingResult | None = None
    recommendation: FinalRecommendation | None = None

    @model_validator(mode="after")
    def _validate_verdict_matches_reasons(self) -> Self:
        expected = FinalRecommendationVerdict.BLOCKED if self.reasons else FinalRecommendationVerdict.ACTIONABLE
        if self.verdict is not expected:
            raise ValueError("verdict must be BLOCKED iff reasons is non-empty")
        return self

    @model_validator(mode="after")
    def _validate_reasons_shape(self) -> Self:
        if len(self.reasons) > 1:
            raise ValueError("reasons must carry at most one reason")
        return self

    @model_validator(mode="after")
    def _validate_recommendation_presence(self) -> Self:
        if self.verdict is FinalRecommendationVerdict.ACTIONABLE:
            if self.recommendation is None:
                raise ValueError("ACTIONABLE requires recommendation")
            if self.recommendation.family is not self.family:
                raise ValueError("recommendation.family must equal the enclosing result's family")
        elif self.recommendation is not None:
            raise ValueError("BLOCKED must not carry recommendation")
        return self

    @model_validator(mode="after")
    def _validate_sizing_result_presence(self) -> Self:
        no_sizing_attempt = bool(self.reasons) and self.reasons[0] in _NO_SIZING_ATTEMPT_REASONS
        if no_sizing_attempt:
            if self.sizing_result is not None:
                raise ValueError(f"{self.reasons[0]} must not carry sizing_result")
        elif self.sizing_result is None:
            raise ValueError("a sizing attempt must have been made: sizing_result is required")
        return self

    @model_validator(mode="after")
    def _validate_sizing_result_outcome_matches_verdict(self) -> Self:
        if self.sizing_result is None:
            return self
        if self.verdict is FinalRecommendationVerdict.ACTIONABLE:
            if self.sizing_result.outcome is not MT5SizingOutcome.ACTIONABLE:
                raise ValueError("ACTIONABLE verdict requires an ACTIONABLE sizing_result")
        else:
            if self.sizing_result.outcome is MT5SizingOutcome.ACTIONABLE:
                raise ValueError("SIZING_NOT_ACTIONABLE must not carry an ACTIONABLE sizing_result")
        return self


class FinalRecommendationConstructionResult(DomainModel):
    """Deterministic Final Recommendation aggregation: one verdict per
    ``StrategySessionResult.family_results`` entry, plus the coarse
    construction outcome - or the pipeline-level fail-closed state when
    Runtime Fact Assembly was never ``READY`` this cycle.

    ``decision_risk_pipeline_result`` is carried unchanged: it is the sole
    audit trail for the entire Stage 5-9 chain this stage never re-embeds
    piecemeal.
    """

    decision_risk_pipeline_result: DecisionRiskPipelineResult
    outcome: FinalRecommendationOutcome
    family_results: tuple[FinalRecommendationFamilyResult, ...]

    @model_validator(mode="after")
    def _validate_pipeline_blocked_before_risk(self) -> Self:
        pipeline_blocked = self.decision_risk_pipeline_result.outcome is DecisionRiskPipelineOutcome.BLOCKED_BEFORE_RISK
        if pipeline_blocked:
            if self.outcome is not FinalRecommendationOutcome.PIPELINE_BLOCKED_BEFORE_RISK:
                raise ValueError("BLOCKED_BEFORE_RISK pipeline result requires PIPELINE_BLOCKED_BEFORE_RISK outcome")
            if self.family_results:
                raise ValueError("PIPELINE_BLOCKED_BEFORE_RISK must not carry family_results")
        elif self.outcome is FinalRecommendationOutcome.PIPELINE_BLOCKED_BEFORE_RISK:
            raise ValueError("PIPELINE_BLOCKED_BEFORE_RISK requires a BLOCKED_BEFORE_RISK pipeline result")
        return self

    @model_validator(mode="after")
    def _validate_family_results_match_session_family_results(self) -> Self:
        session_result = self.decision_risk_pipeline_result.strategy_session_result
        if session_result is None:
            return self
        expected = tuple(result.family for result in session_result.family_results)
        actual = tuple(result.family for result in self.family_results)
        if actual != expected:
            raise ValueError("family_results must cover exactly strategy_session_result.family_results, in the same order")
        return self

    @model_validator(mode="after")
    def _validate_outcome(self) -> Self:
        if self.decision_risk_pipeline_result.outcome is DecisionRiskPipelineOutcome.BLOCKED_BEFORE_RISK:
            return self
        any_actionable = any(result.verdict is FinalRecommendationVerdict.ACTIONABLE for result in self.family_results)
        expected = FinalRecommendationOutcome.SOME_ACTIONABLE if any_actionable else FinalRecommendationOutcome.NO_ACTIONABLE_FAMILY
        if self.outcome is not expected:
            raise ValueError(f"outcome {self.outcome} does not match per-family-derived outcome {expected}")
        return self


__all__ = ["FinalRecommendation", "FinalRecommendationConstructionResult", "FinalRecommendationFamilyResult"]
