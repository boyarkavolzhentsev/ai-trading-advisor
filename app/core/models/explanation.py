"""LLM Explanation Layer output contracts.

Two disjoint kinds of model live here, never mixed on one class:

AUTHORITATIVE (``RecommendationFactCard``, ``TrackingFactCard``) - typed,
Decimal/enum-valued, copied unchanged from ``RuntimeCycleResult``'s own
embedded ``FinalRecommendation``/``PositionRecord``/``MT5TrackedRecommendation``/
``FinalRecommendationProvenance`` facts. These are what an API/Telegram
consumer reads for every trading fact - direction, symbol, entry, stop, TP,
volume, approved risk, account currency, lifecycle status, PnL. The LLM never
produces, sees unchanged, or can shadow these: they are never serialized
into an LLM prompt in their typed form (see ``ExplanationContext``) and never
constructible from LLM output (``RecommendationExplanation``/
``TrackingExplanation`` carry no numeric/enum trading field at all).

NARRATIVE (``GroundedFact``, ``ExplanationContext``, ``RecommendationExplanation``,
``TrackingExplanation``, ``ExplanationNarrative``) - the LLM-visible input and
LLM-produced output. Every numeric/enum value the LLM is allowed to see is
pre-formatted to a plain string by the deterministic context builder (see
``app.orchestration.explanation``) before construction - the LLM is never
handed a raw ``Decimal``/enum object, and its own output schema
(``ExplanationNarrative``) has no field capable of asserting a new
authoritative fact.

``ExplanationResult`` is the final combined output: authoritative cards and
LLM (or deterministic-fallback) narrative side by side, matched 1:1 by
``trade_id``/order - never requiring a downstream consumer to parse a
trading fact out of prose.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Self

from pydantic import Field, model_validator

from app.core.enums.explanation import ExplanationContentStatus, ExplanationProviderStatus
from app.core.enums.mt5_matching import MT5TrackedRecommendationCreationOutcome
from app.core.enums.strategy_router import StrategyFamily
from app.core.enums.trade import TradeDirection, TradeStatus
from app.core.models.base import DomainModel, Price, Symbol, Timestamp

# --- authoritative cards -----------------------------------------------


class RecommendationFactCard(DomainModel):
    """One ACTIONABLE ``FinalRecommendation``'s authoritative facts, plus
    this cycle's Part E tracking-creation outcome for it if one was
    attempted. Never produced from, or overridable by, LLM output.

    ``tracking_creation_outcome``/``tracking_persisted``/``provenance_persisted``
    are all ``None`` together when no tracking-creation attempt was made for
    this trade_id this cycle (e.g. a NETTING/UNKNOWN issuance guard withheld
    it) - never fabricated as if creation had been attempted.
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
    tracking_creation_outcome: MT5TrackedRecommendationCreationOutcome | None = None
    tracking_persisted: bool | None = None
    provenance_persisted: bool | None = None


class TrackingFactCard(DomainModel):
    """One tracked recommendation's authoritative lifecycle facts this
    cycle - built from Stage 10E's own unchanged ``PositionRecord``/
    ``MT5TrackedRecommendation`` state (existing advancement) or from a
    freshly ``CREATED`` Part E result. Never a prediction, never a
    recalculated PnL.

    ``account_currency`` is ``None`` for an existing (previously-issued)
    tracked recommendation being advanced this cycle: Part E's durable
    provenance (the sole carrier of ``account_currency`` for a tracked
    recommendation) is deliberately not read during normal Stage 10E
    lifecycle advancement (see ``app.mt5.recommendation_provenance_persistence``) -
    never fabricated here either.
    """

    trade_id: Annotated[str, Field(min_length=1)]
    symbol: Symbol
    status: TradeStatus
    matched_position_id: Annotated[int, Field(gt=0)] | None = None
    pnl: Decimal | None = None
    account_currency: Annotated[str, Field(min_length=1)] | None = None


# --- LLM-visible / LLM-produced narrative -------------------------------


class GroundedFact(DomainModel):
    """One deterministic fact, pre-formatted to a plain string - the only
    unit ever serialized into the LLM prompt. ``fact_id`` is a stable,
    deterministic dotted path (never random/UUID/object-id) tied to the
    exact source semantics it was read from."""

    fact_id: Annotated[str, Field(min_length=1)]
    label: Annotated[str, Field(min_length=1)]
    value: str


class UntrustedTextBlock(DomainModel):
    """One block of caller-supplied free text - always DATA, never
    instructions, regardless of content. Empty in V1 (see
    ``app.orchestration.explanation``'s own docstring) - reserved so the
    boundary is load-bearing before any future stage reintroduces raw
    external text."""

    source: Annotated[str, Field(min_length=1)]
    text: str


class ExplanationContext(DomainModel):
    """The ONLY object ever serialized into an LLM prompt.

    ``recommendation_facts``/``tracking_facts`` are one ``GroundedFact``
    group per ``RecommendationFactCard``/``TrackingFactCard``, in the exact
    same order the cards themselves were built in (``family_results`` order
    for recommendations - never reordered, never ranked). Never embeds a
    ``RecommendationFactCard``/``TrackingFactCard`` object directly.
    """

    as_of: Timestamp
    facts: tuple[GroundedFact, ...] = ()
    recommendation_facts: tuple[tuple[GroundedFact, ...], ...] = ()
    tracking_facts: tuple[tuple[GroundedFact, ...], ...] = ()
    warnings: tuple[GroundedFact, ...] = ()
    untrusted_text: tuple[UntrustedTextBlock, ...] = ()


class ExplanationRequest(DomainModel):
    """One LLM provider call's complete input. ``previous_validation_error``
    is populated only on the single permitted retry (see
    ``app.orchestration.explanation.explain_runtime_cycle``) - never on the
    first attempt."""

    context: ExplanationContext
    previous_validation_error: str | None = None


class RecommendationExplanation(DomainModel):
    """LLM-generated narrative for one recommendation - explanatory only.
    Carries no numeric/enum trading field: it can never shadow, replace, or
    disagree with the authoritative ``RecommendationFactCard`` it accompanies."""

    trade_id: Annotated[str, Field(min_length=1)]
    family: StrategyFamily
    narrative: Annotated[str, Field(min_length=1)]
    cited_fact_ids: tuple[str, ...] = ()


class TrackingExplanation(DomainModel):
    """LLM-generated narrative for one tracked recommendation - explanatory
    only, mirrors ``RecommendationExplanation``'s own discipline."""

    trade_id: Annotated[str, Field(min_length=1)]
    narrative: Annotated[str, Field(min_length=1)]
    cited_fact_ids: tuple[str, ...] = ()


class ExplanationNarrative(DomainModel):
    """The complete LLM structured-output schema - the only shape a
    provider's raw output is validated against. Contains no authoritative
    trading field anywhere: every value here is prose, matched against the
    caller-owned cards only by ``trade_id``/order after validation (see
    ``app.orchestration.explanation._validate_narrative``)."""

    headline: Annotated[str, Field(min_length=1)]
    cycle_summary: Annotated[str, Field(min_length=1)]
    recommendation_explanations: tuple[RecommendationExplanation, ...] = ()
    tracking_explanations: tuple[TrackingExplanation, ...] = ()
    no_trade_explanation: str | None = None
    warnings: tuple[str, ...] = ()
    data_quality_notes: tuple[str, ...] = ()
    risk_notes: tuple[str, ...] = ()


class ExplanationLLMResponse(DomainModel):
    """One provider call's raw result.

    ``narrative`` is ``None`` when the provider responded but its raw output
    could not be parsed/validated into ``ExplanationNarrative``'s own schema
    - a normal, non-exceptional provider outcome that triggers exactly one
    retry (see ``app.orchestration.explanation``). A provider call that
    cannot complete at all (network failure, timeout, provider outage) must
    raise instead of returning this model with ``narrative=None`` - raising
    is the only signal orchestration treats as
    ``ExplanationProviderStatus.LLM_UNAVAILABLE`` (no retry attempted).
    """

    narrative: ExplanationNarrative | None = None


# --- final combined output ----------------------------------------------


class ExplanationResult(DomainModel):
    """The final, typed explanation for one runtime cycle: authoritative
    cards and narrative side by side, matched 1:1 by ``trade_id``/order -
    never requiring a downstream consumer to parse a trading fact out of
    prose. Constructible either from validated LLM output or from the
    deterministic fallback formatter - both paths satisfy the identical
    1:1/no-duplicate invariants enforced below.
    """

    content_status: ExplanationContentStatus
    provider_status: ExplanationProviderStatus
    headline: Annotated[str, Field(min_length=1)]
    cycle_summary: Annotated[str, Field(min_length=1)]
    recommendation_cards: tuple[RecommendationFactCard, ...] = ()
    recommendation_explanations: tuple[RecommendationExplanation, ...] = ()
    tracking_cards: tuple[TrackingFactCard, ...] = ()
    tracking_explanations: tuple[TrackingExplanation, ...] = ()
    no_trade_explanation: str | None = None
    warnings: tuple[str, ...] = ()
    data_quality_notes: tuple[str, ...] = ()
    risk_notes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _validate_recommendation_explanations_match_cards(self) -> Self:
        if len(self.recommendation_explanations) != len(self.recommendation_cards):
            raise ValueError("recommendation_explanations must match recommendation_cards 1:1")
        for explanation, card in zip(self.recommendation_explanations, self.recommendation_cards):
            if explanation.trade_id != card.trade_id or explanation.family is not card.family:
                raise ValueError("recommendation_explanations must match recommendation_cards by trade_id/family, in order")
        return self

    @model_validator(mode="after")
    def _validate_tracking_explanations_match_cards(self) -> Self:
        if len(self.tracking_explanations) != len(self.tracking_cards):
            raise ValueError("tracking_explanations must match tracking_cards 1:1")
        for explanation, card in zip(self.tracking_explanations, self.tracking_cards):
            if explanation.trade_id != card.trade_id:
                raise ValueError("tracking_explanations must match tracking_cards by trade_id, in order")
        return self

    @model_validator(mode="after")
    def _validate_no_duplicate_trade_ids(self) -> Self:
        recommendation_ids = [card.trade_id for card in self.recommendation_cards]
        if len(set(recommendation_ids)) != len(recommendation_ids):
            raise ValueError("recommendation_cards must not contain duplicate trade_id values")
        tracking_ids = [card.trade_id for card in self.tracking_cards]
        if len(set(tracking_ids)) != len(tracking_ids):
            raise ValueError("tracking_cards must not contain duplicate trade_id values")
        return self


__all__ = [
    "ExplanationContext",
    "ExplanationLLMResponse",
    "ExplanationNarrative",
    "ExplanationRequest",
    "ExplanationResult",
    "GroundedFact",
    "RecommendationExplanation",
    "RecommendationFactCard",
    "TrackingExplanation",
    "TrackingFactCard",
    "UntrustedTextBlock",
]
