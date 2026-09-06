"""LLM Explanation Layer (NEXT STAGE, Core).

Explains one already-completed ``RuntimeCycleResult`` to a human. The
deterministic engine remains sole authority: this layer never makes a
trading decision, never changes direction/entry/stop/TP/volume/approved
risk/account currency, never selects a strategy family, never overrides a
Policy/Risk/Portfolio/Session/NETTING-guard outcome, never converts a
blocked/no-trade cycle into an actionable one, and never places or modifies
an MT5 order. It only narrates already-decided facts.

Three responsibilities, composed from narrowest to broadest, mirroring the
Part F pure/impure split:

``build_recommendation_cards``/``build_tracking_cards`` - pure, deterministic
projection of ``RuntimeCycleResult`` onto authoritative, typed
``RecommendationFactCard``/``TrackingFactCard`` objects. These are what an
API/Telegram consumer reads for every trading fact - never derived from, or
overridable by, LLM output.

``build_explanation_context`` - pure, deterministic projection of those same
cards (plus cycle-level facts) into the ONLY object ever serialized into an
LLM prompt: ``ExplanationContext``, whose every leaf value is a
pre-formatted plain string (see ``_format_decimal``) - never a raw
``Decimal``/enum the LLM could be tempted to recompute from.

``explain_runtime_cycle`` - the single impure orchestration entry point: at
most one provider call, at most one retry on invalid structured output
(never on a raised/unavailable provider), post-validation of every cited
fact ID and every recommendation/tracking narrative's 1:1 correspondence to
the authoritative cards, and a pure deterministic fallback
(``render_deterministic_fallback``) whenever the LLM path does not produce a
validated result. ``RuntimeCycleResult`` itself is never mutated by any
function here - it is read-only input throughout.

Architectural boundary (locked): ``RuntimeCycleResult`` flows through the
deterministic builder exactly once, producing ``ExplanationContext`` plus the
authoritative cards - every downstream consumer (the LLM prompt AND the
deterministic fallback) is confined to that already-reduced representation
and never reaches back around it to re-read ``RuntimeCycleResult`` directly.
``render_deterministic_fallback`` therefore accepts ``ExplanationContext``,
never ``RuntimeCycleResult`` - any cycle-level branching it needs (outcome,
connectivity state, netting-guard cause, degraded-cause warnings) is looked
up by stable ``fact_id`` via ``_lookup_fact``/``context.warnings``, exactly
the same facts the LLM itself would have seen.

Untrusted external text (``UntrustedTextBlock``) is a reserved, currently-
empty boundary: no raw free text (a news headline, an analyst's own prose)
is reachable from ``RuntimeCycleResult`` today - every External Intelligence
fact embedded in ``DecisionRiskPipelineResult`` is already reduced to a
short, structured ``observed_value``/``reference_value`` string well before
Stage 5 (Stage 4F's own "no interpretation" discipline, independently
enforced by its own existing test suite) - so this layer has nothing
untrusted to carry in V1. The boundary exists so a future stage that does
reintroduce raw text is never the first thing to define it.
"""

from __future__ import annotations

from decimal import Decimal

from app.core.enums.explanation import ExplanationContentStatus, ExplanationProviderStatus
from app.core.enums.mt5_matching import MT5TrackedRecommendationCreationOutcome
from app.core.enums.mt5_rollover import MT5RolloverOutcome
from app.core.enums.mt5_runtime import AccountPositionMode
from app.core.enums.runtime_cycle import NettingIssuanceOutcome, RuntimeCycleOutcome
from app.core.enums.trade import TradeStatus
from app.core.models.explanation import (
    ExplanationContext,
    ExplanationLLMResponse,
    ExplanationNarrative,
    ExplanationRequest,
    ExplanationResult,
    GroundedFact,
    RecommendationExplanation,
    RecommendationFactCard,
    TrackingExplanation,
    TrackingFactCard,
)
from app.core.models.runtime_cycle import RuntimeCycleResult
from app.llm.protocols import ExplanationLLMClient

_USABLE_ROLLOVER_OUTCOMES: frozenset[MT5RolloverOutcome] = frozenset(
    {MT5RolloverOutcome.READY, MT5RolloverOutcome.BOOTSTRAPPED_MIDDAY}
)
"""A locally-owned copy of the usable-outcome set - mirrors the Stage
5A/6A/6C/7/8/9/10B/10C/10D/Part-F precedent of maintaining an independent
copy rather than cross-importing one from ``app.mt5.rollover``."""

_NETTING_BLOCK_OUTCOMES: frozenset[NettingIssuanceOutcome] = frozenset(
    {
        NettingIssuanceOutcome.BLOCKED_EXISTING_BROKER_POSITION,
        NettingIssuanceOutcome.BLOCKED_EXISTING_UNRESOLVED_RECOMMENDATION,
        NettingIssuanceOutcome.BLOCKED_MULTIPLE_ACTIONABLE_RECOMMENDATIONS,
    }
)
"""``NettingIssuanceOutcome`` members that represent an actual issuance/
tracking-safety restriction - never a strategy rejection. ``ALLOWED`` and
``NO_ACTIONABLE_RECOMMENDATIONS`` are deliberately excluded: neither is a
restriction worth warning about (the latter is business no-trade, see
``_build_no_trade_explanation``)."""

_NETTING_BLOCK_LABELS: dict[NettingIssuanceOutcome, str] = {
    NettingIssuanceOutcome.BLOCKED_EXISTING_BROKER_POSITION: "an existing broker position already exists on this symbol",
    NettingIssuanceOutcome.BLOCKED_EXISTING_UNRESOLVED_RECOMMENDATION: (
        "a previously issued recommendation on this symbol is still pending or open"
    ),
    NettingIssuanceOutcome.BLOCKED_MULTIPLE_ACTIONABLE_RECOMMENDATIONS: (
        "multiple strategies qualified simultaneously on a netting-style account, and none can be "
        "safely distinguished, so all were withheld"
    ),
}
"""Fixed, non-LLM-generated wording for each NETTING/UNKNOWN safety
restriction - shared verbatim between the LLM system-prompt guidance and the
deterministic fallback (``render_deterministic_fallback``) so the two never
describe the same restriction differently. These are issuance/tracking-
safety restrictions, never strategy rejections - the wording says so
explicitly in every case."""

_TRACKING_STATUS_LABELS: dict[TradeStatus, str] = {
    TradeStatus.PENDING: "awaiting broker fill confirmation",
    TradeStatus.OPEN: "matched to a broker position and currently open",
    TradeStatus.WIN: "closed with a profit",
    TradeStatus.LOSS: "closed with a loss",
    TradeStatus.BREAKEVEN: "closed at breakeven",
    TradeStatus.NOT_FILLED: "execution window closed without a confirmed fill",
}
"""Fixed wording for every ``TradeStatus`` Stage 10E can actually produce
(``PENDING``/``OPEN``/``WIN``/``LOSS``/``BREAKEVEN``/``NOT_FILLED`` - see
``app.core.models.mt5_tracking``'s own reachable-status precedent). Never
predicts a fill, never infers broker execution beyond what the status
already states, never recalculates PnL."""


def _format_decimal(value: Decimal) -> str:
    """Canonical, deterministic string representation - fixed-point, never
    scientific notation, never rounded, never unit-converted."""
    return format(value, "f")


def _format_price_levels(levels: tuple[Decimal, ...]) -> str:
    if not levels:
        return "none"
    return ", ".join(_format_decimal(level) for level in levels)


def _format_pnl_suffix(card: TrackingFactCard) -> str:
    """A known ``pnl`` is never suppressed merely because ``account_currency``
    happens to be unavailable (e.g. an existing tracked recommendation being
    advanced, whose durable provenance is not read during normal Stage 10E
    advancement - see ``build_tracking_cards``) - the currency label is
    appended only when it is itself known."""
    if card.pnl is None:
        return ""
    if card.account_currency:
        return f", PnL {_format_decimal(card.pnl)} {card.account_currency}"
    return f", PnL {_format_decimal(card.pnl)}"


# --- authoritative card construction (pure) -----------------------------


def build_recommendation_cards(result: RuntimeCycleResult) -> tuple[RecommendationFactCard, ...]:
    """One ``RecommendationFactCard`` per ACTIONABLE ``FinalRecommendation``,
    in exact ``family_results`` order - never sorted, never ranked, never
    reduced to a single "best" recommendation. A family with no tracking-
    creation attempt this cycle (e.g. withheld by the NETTING/UNKNOWN guard)
    correctly carries ``tracking_creation_outcome=None`` rather than a
    fabricated outcome.
    """
    final = result.final_recommendation_construction_result
    if final is None:
        return ()

    persistence_by_trade_id = {entry.trade_id: entry for entry in result.new_tracking_persistence_outcomes}

    cards: list[RecommendationFactCard] = []
    for family_result in final.family_results:
        recommendation = family_result.recommendation
        if recommendation is None:
            continue
        persistence = persistence_by_trade_id.get(recommendation.trade_id)
        cards.append(
            RecommendationFactCard(
                trade_id=recommendation.trade_id,
                family=recommendation.family,
                symbol=recommendation.symbol,
                direction=recommendation.direction,
                entry_price=recommendation.entry_price,
                stop_loss=recommendation.stop_loss,
                take_profit_levels=recommendation.take_profit_levels,
                approved_volume=recommendation.approved_volume,
                approved_risk_amount=recommendation.approved_risk_amount,
                account_currency=recommendation.account_currency,
                tracking_creation_outcome=persistence.tracking_creation_outcome if persistence is not None else None,
                tracking_persisted=persistence.tracking_persisted if persistence is not None else None,
                provenance_persisted=persistence.provenance_persisted if persistence is not None else None,
            )
        )
    return tuple(cards)


def build_tracking_cards(result: RuntimeCycleResult) -> tuple[TrackingFactCard, ...]:
    """One ``TrackingFactCard`` per existing tracked recommendation advanced
    this cycle, plus one per freshly ``CREATED`` recommendation - using only
    Stage 10E's own unchanged ``PositionRecord``/``MT5TrackedRecommendation``
    state. Never predicts a fill, never recalculates PnL, never manually
    re-matches a position."""
    cards: list[TrackingFactCard] = []

    for entry in result.advanced_tracking:
        record = entry.tracked_recommendation.position_record
        cards.append(
            TrackingFactCard(
                trade_id=entry.trade_id,
                symbol=record.symbol,
                status=record.status,
                matched_position_id=entry.tracked_recommendation.matched_position_id,
                pnl=record.pnl,
                # a direct, unconverted copy of the SAME cycle's already-confirmed
                # broker account currency (an MT5 account's deposit currency is
                # fixed for the account's lifetime, so the current read is always
                # valid for interpreting any PositionRecord.pnl regardless of
                # which cycle's deal history actually produced it) - never Part
                # E's provenance (not read during normal advancement) and never
                # fabricated: None only in the narrow, legitimate case where
                # account_facts itself is unavailable this cycle.
                account_currency=result.account_facts.currency if result.account_facts is not None else None,
            )
        )

    for tracking_result in result.new_tracking_results:
        if tracking_result.tracking_creation_result.outcome is not MT5TrackedRecommendationCreationOutcome.CREATED:
            continue
        tracked = tracking_result.tracking_creation_result.tracked_recommendation
        assert tracked is not None
        record = tracked.position_record
        cards.append(
            TrackingFactCard(
                trade_id=tracking_result.trade_id,
                symbol=record.symbol,
                status=record.status,
                matched_position_id=tracked.matched_position_id,
                pnl=record.pnl,
                account_currency=tracking_result.provenance.account_currency,
            )
        )

    return tuple(cards)


# --- LLM-visible context construction (pure) ----------------------------


def _project_recommendation_card(card: RecommendationFactCard) -> tuple[GroundedFact, ...]:
    prefix = f"recommendation.{card.trade_id}"
    facts = [
        GroundedFact(fact_id=f"{prefix}.family", label="Family", value=card.family.value),
        GroundedFact(fact_id=f"{prefix}.symbol", label="Symbol", value=card.symbol),
        GroundedFact(fact_id=f"{prefix}.direction", label="Direction", value=card.direction.value),
        GroundedFact(fact_id=f"{prefix}.entry_price", label="Entry price", value=_format_decimal(card.entry_price)),
        GroundedFact(fact_id=f"{prefix}.stop_loss", label="Stop loss", value=_format_decimal(card.stop_loss)),
        GroundedFact(
            fact_id=f"{prefix}.take_profit_levels", label="Take-profit levels", value=_format_price_levels(card.take_profit_levels)
        ),
        GroundedFact(fact_id=f"{prefix}.approved_volume", label="Approved volume", value=_format_decimal(card.approved_volume)),
        GroundedFact(
            fact_id=f"{prefix}.approved_risk_amount", label="Approved risk amount", value=_format_decimal(card.approved_risk_amount)
        ),
        GroundedFact(fact_id=f"{prefix}.account_currency", label="Account currency", value=card.account_currency),
    ]
    if card.tracking_creation_outcome is not None:
        facts.append(
            GroundedFact(
                fact_id=f"{prefix}.tracking_creation_outcome",
                label="Tracking creation outcome",
                value=card.tracking_creation_outcome.value,
            )
        )
    if card.tracking_persisted is not None:
        facts.append(GroundedFact(fact_id=f"{prefix}.tracking_persisted", label="Tracking persisted", value=str(card.tracking_persisted)))
    if card.provenance_persisted is not None:
        facts.append(
            GroundedFact(fact_id=f"{prefix}.provenance_persisted", label="Provenance persisted", value=str(card.provenance_persisted))
        )
    return tuple(facts)


def _project_tracking_card(card: TrackingFactCard) -> tuple[GroundedFact, ...]:
    prefix = f"tracking.{card.trade_id}"
    facts = [
        GroundedFact(fact_id=f"{prefix}.symbol", label="Symbol", value=card.symbol),
        GroundedFact(fact_id=f"{prefix}.status", label="Status", value=card.status.value),
    ]
    if card.matched_position_id is not None:
        facts.append(
            GroundedFact(fact_id=f"{prefix}.matched_position_id", label="Matched position id", value=str(card.matched_position_id))
        )
    if card.pnl is not None:
        facts.append(GroundedFact(fact_id=f"{prefix}.pnl", label="PnL", value=_format_decimal(card.pnl)))
    if card.account_currency is not None:
        facts.append(GroundedFact(fact_id=f"{prefix}.account_currency", label="Account currency", value=card.account_currency))
    return tuple(facts)


def _build_cycle_facts(result: RuntimeCycleResult) -> tuple[GroundedFact, ...]:
    """Stable, explicit field order - never reordered across identical
    inputs."""
    facts: list[GroundedFact] = [
        GroundedFact(fact_id="runtime.outcome", label="Runtime cycle outcome", value=result.outcome.value),
        GroundedFact(
            fact_id="runtime.mt5_runtime_status.state", label="MT5 connectivity state", value=result.mt5_runtime_status.state.value
        ),
    ]
    if result.mt5_runtime_status.reason is not None:
        facts.append(
            GroundedFact(fact_id="runtime.mt5_runtime_status.reason", label="MT5 connectivity reason", value=result.mt5_runtime_status.reason)
        )
    if result.account_position_mode is not None:
        facts.append(
            GroundedFact(fact_id="runtime.account_position_mode", label="Account position mode", value=result.account_position_mode.value)
        )
    if result.positions_read_status is not None:
        facts.append(GroundedFact(fact_id="runtime.positions_read_status", label="Positions read status", value=result.positions_read_status))
    if result.history_read_status is not None:
        facts.append(GroundedFact(fact_id="runtime.history_read_status", label="History read status", value=result.history_read_status))
    if result.target_symbol_facts_available is not None:
        facts.append(
            GroundedFact(
                fact_id="runtime.target_symbol_facts_available",
                label="Target symbol facts available",
                value=str(result.target_symbol_facts_available),
            )
        )
    if result.account_facts is not None:
        facts.append(GroundedFact(fact_id="runtime.account_currency", label="Account currency", value=result.account_facts.currency))
    if result.rollover_snapshot is not None:
        facts.append(GroundedFact(fact_id="rollover.outcome", label="Rollover outcome", value=result.rollover_snapshot.rollover_outcome.value))
    if result.open_risk_assessment is not None:
        facts.append(GroundedFact(fact_id="open_risk.outcome", label="Open risk assessment outcome", value=result.open_risk_assessment.outcome.value))
    if result.realized_daily_pnl_assessment is not None:
        facts.append(
            GroundedFact(
                fact_id="realized_pnl.outcome", label="Realized daily PnL outcome", value=result.realized_daily_pnl_assessment.outcome.value
            )
        )
    if result.account_risk_snapshot_assembly is not None:
        facts.append(
            GroundedFact(
                fact_id="account_risk_snapshot_assembly.outcome",
                label="Account risk snapshot assembly outcome",
                value=result.account_risk_snapshot_assembly.outcome.value,
            )
        )
    if result.decision_risk_pipeline_result is not None:
        facts.append(
            GroundedFact(
                fact_id="decision_risk_pipeline.outcome",
                label="Decision/risk pipeline outcome",
                value=result.decision_risk_pipeline_result.outcome.value,
            )
        )
    if result.final_recommendation_construction_result is not None:
        facts.append(
            GroundedFact(
                fact_id="final_recommendation.outcome",
                label="Final recommendation outcome",
                value=result.final_recommendation_construction_result.outcome.value,
            )
        )
    if result.netting_guard_result is not None:
        facts.append(GroundedFact(fact_id="netting_guard.outcome", label="Netting guard outcome", value=result.netting_guard_result.outcome.value))
        facts.append(
            GroundedFact(
                fact_id="netting_guard.account_position_mode",
                label="Netting guard account position mode",
                value=result.netting_guard_result.account_position_mode.value,
            )
        )
    return tuple(facts)


def _build_warnings(result: RuntimeCycleResult) -> tuple[GroundedFact, ...]:
    """One distinct ``GroundedFact`` per actual degraded cause present -
    never a single generic warning, never fabricated for a condition that
    did not occur."""
    warnings: list[GroundedFact] = []

    for excluded in result.excluded_tracked_recommendations:
        warnings.append(
            GroundedFact(
                fact_id=f"warning.excluded_tracking.{excluded.trade_id}",
                label="Excluded tracked recommendation",
                value=f"{excluded.trade_id}: {excluded.read_status}",
            )
        )

    for entry in result.advanced_tracking:
        if not entry.persisted:
            warnings.append(
                GroundedFact(
                    fact_id=f"warning.tracking_persistence_failed.{entry.trade_id}",
                    label="Tracking persistence failure",
                    value=entry.trade_id,
                )
            )

    for outcome_entry in result.new_tracking_persistence_outcomes:
        if outcome_entry.tracking_creation_outcome is not MT5TrackedRecommendationCreationOutcome.CREATED:
            continue
        if not outcome_entry.tracking_persisted:
            warnings.append(
                GroundedFact(
                    fact_id=f"warning.tracking_persistence_failed.{outcome_entry.trade_id}",
                    label="Tracking persistence failure",
                    value=outcome_entry.trade_id,
                )
            )
        if not outcome_entry.provenance_persisted:
            warnings.append(
                GroundedFact(
                    fact_id=f"warning.provenance_persistence_failed.{outcome_entry.trade_id}",
                    label="Provenance persistence failure",
                    value=outcome_entry.trade_id,
                )
            )

    if result.netting_guard_result is not None and result.netting_guard_result.outcome in _NETTING_BLOCK_OUTCOMES:
        warnings.append(
            GroundedFact(
                fact_id="warning.netting_guard_blocked",
                label="Issuance withheld (account-position-mode safety)",
                value=f"{result.netting_guard_result.symbol}: {result.netting_guard_result.outcome.value}",
            )
        )

    if result.target_symbol_facts_available is False:
        warnings.append(
            GroundedFact(fact_id="warning.target_symbol_facts_unavailable", label="Target symbol facts unavailable", value="False")
        )

    if result.positions_read_status is not None and result.positions_read_status != "OK":
        warnings.append(
            GroundedFact(fact_id="warning.positions_unavailable", label="Positions read unavailable", value=result.positions_read_status)
        )

    if result.history_read_status is not None and result.history_read_status != "OK":
        warnings.append(
            GroundedFact(fact_id="warning.history_unavailable", label="History read unavailable", value=result.history_read_status)
        )

    if result.rollover_snapshot is not None and result.rollover_snapshot.rollover_outcome not in _USABLE_ROLLOVER_OUTCOMES:
        warnings.append(
            GroundedFact(
                fact_id="warning.rollover_unusable", label="Rollover unusable", value=result.rollover_snapshot.rollover_outcome.value
            )
        )

    return tuple(warnings)


def build_explanation_context(result: RuntimeCycleResult) -> ExplanationContext:
    """Pure. No wall clock, no randomness, no filesystem, no network, no LLM
    call, no MT5 call, no persistence - a deterministic, synchronous
    function of ``result`` alone."""
    recommendation_cards = build_recommendation_cards(result)
    tracking_cards = build_tracking_cards(result)
    return ExplanationContext(
        as_of=result.as_of,
        facts=_build_cycle_facts(result),
        recommendation_facts=tuple(_project_recommendation_card(card) for card in recommendation_cards),
        tracking_facts=tuple(_project_tracking_card(card) for card in tracking_cards),
        warnings=_build_warnings(result),
    )


# --- deterministic fallback (pure) --------------------------------------


def _lookup_fact(context: ExplanationContext, fact_id: str) -> str | None:
    """The sole way ``render_deterministic_fallback`` reads a cycle-level
    fact - by stable ``fact_id`` against ``context.facts``, never by reaching
    back around to ``RuntimeCycleResult``. Returns ``None`` when the fact was
    never projected (e.g. its underlying ``RuntimeCycleResult`` field was
    itself ``None`` this cycle) - never fabricated."""
    for fact in context.facts:
        if fact.fact_id == fact_id:
            return fact.value
    return None


def _render_warning(fact: GroundedFact, context: ExplanationContext) -> str:
    """Fixed, deterministic wording per warning ``fact_id`` - the same
    dispatch a caller could perform themselves from ``context.warnings``
    alone. Falls back to a generic ``label: value`` rendering for any warning
    ``fact_id`` not given a bespoke template (never drops a warning silently)."""
    if fact.fact_id.startswith("warning.excluded_tracking."):
        trade_id, _, read_status = fact.value.partition(": ")
        return f"Tracked recommendation {trade_id} could not be loaded ({read_status}) and was excluded."
    if fact.fact_id.startswith("warning.tracking_persistence_failed."):
        return f"Failed to persist tracking state for {fact.value}."
    if fact.fact_id.startswith("warning.provenance_persistence_failed."):
        return f"Failed to persist provenance record for {fact.value}."
    if fact.fact_id == "warning.netting_guard_blocked":
        symbol, _, outcome_value = fact.value.partition(": ")
        label = _NETTING_BLOCK_LABELS.get(NettingIssuanceOutcome(outcome_value), outcome_value)
        account_position_mode_value = _lookup_fact(context, "netting_guard.account_position_mode")
        mode_note = (
            " (the account's position-netting mode could not be determined, so conservative netting-style "
            "restrictions were applied)"
            if account_position_mode_value == AccountPositionMode.UNKNOWN.value
            else ""
        )
        return f"New recommendation issuance was withheld for {symbol}: {label}{mode_note}."
    if fact.fact_id == "warning.target_symbol_facts_unavailable":
        return "Target symbol broker facts were unavailable this cycle; new-recommendation issuance could not complete."
    if fact.fact_id == "warning.positions_unavailable":
        return f"Broker open-position read was unavailable this cycle ({fact.value})."
    if fact.fact_id == "warning.history_unavailable":
        return f"Broker deal-history read was unavailable this cycle ({fact.value})."
    if fact.fact_id == "warning.rollover_unusable":
        return f"Rollover state was not usable this cycle ({fact.value})."
    return f"{fact.label}: {fact.value}."


def _build_no_trade_explanation(context: ExplanationContext, recommendation_cards: tuple[RecommendationFactCard, ...]) -> str | None:
    if recommendation_cards:
        return None
    final_outcome_value = _lookup_fact(context, "final_recommendation.outcome")
    if final_outcome_value is None:
        return None
    return f"No actionable recommendation this cycle ({final_outcome_value})."


def render_deterministic_fallback(
    *,
    context: ExplanationContext,
    recommendation_cards: tuple[RecommendationFactCard, ...],
    tracking_cards: tuple[TrackingFactCard, ...],
    provider_status: ExplanationProviderStatus,
) -> ExplanationResult:
    """Pure. Works without any LLM client and without ``RuntimeCycleResult``
    - confined entirely to the already-built ``ExplanationContext`` (the same
    facts the LLM itself would have been given) and the already-built
    authoritative cards. Fixed templates only - never invents a causal
    explanation, never performs a new business calculation."""
    recommendation_explanations = tuple(
        RecommendationExplanation(
            trade_id=card.trade_id,
            family=card.family,
            narrative=(
                f"{card.family.value} recommendation: {card.direction.value} {card.symbol}, "
                f"entry {_format_decimal(card.entry_price)}, stop {_format_decimal(card.stop_loss)}, "
                f"take-profit {_format_price_levels(card.take_profit_levels)}, "
                f"volume {_format_decimal(card.approved_volume)}, "
                f"approved risk {_format_decimal(card.approved_risk_amount)} {card.account_currency}."
            ),
        )
        for card in recommendation_cards
    )

    tracking_explanations = tuple(
        TrackingExplanation(
            trade_id=card.trade_id,
            narrative=(
                f"{card.symbol}: {_TRACKING_STATUS_LABELS.get(card.status, card.status.value)}" + _format_pnl_suffix(card) + "."
            ),
        )
        for card in tracking_cards
    )

    no_trade_explanation = _build_no_trade_explanation(context, recommendation_cards)

    runtime_outcome_value = _lookup_fact(context, "runtime.outcome")
    if runtime_outcome_value == RuntimeCycleOutcome.BLOCKED.value:
        headline = "Runtime cycle blocked"
        state_value = _lookup_fact(context, "runtime.mt5_runtime_status.state") or "UNKNOWN"
        reason_value = _lookup_fact(context, "runtime.mt5_runtime_status.reason")
        reason = f" ({reason_value})" if reason_value else ""
        cycle_summary = f"MT5 connectivity unavailable: {state_value}{reason}."
    elif recommendation_cards:
        headline = f"{len(recommendation_cards)} actionable recommendation(s)"
        cycle_summary = "The deterministic engine produced one or more actionable recommendations this cycle."
    elif no_trade_explanation is not None:
        headline = "No trade this cycle"
        cycle_summary = no_trade_explanation
    else:
        headline = "Runtime cycle degraded" if runtime_outcome_value == RuntimeCycleOutcome.PARTIAL_DEGRADED.value else "Runtime cycle complete"
        cycle_summary = f"Cycle outcome: {runtime_outcome_value}."

    warnings = tuple(_render_warning(fact, context) for fact in context.warnings)

    return ExplanationResult(
        content_status=ExplanationContentStatus.AVAILABLE,
        provider_status=provider_status,
        headline=headline,
        cycle_summary=cycle_summary,
        recommendation_cards=recommendation_cards,
        recommendation_explanations=recommendation_explanations,
        tracking_cards=tracking_cards,
        tracking_explanations=tracking_explanations,
        no_trade_explanation=no_trade_explanation,
        warnings=warnings,
    )


# --- LLM narrative validation (pure) -------------------------------------


def _all_context_fact_ids(context: ExplanationContext) -> frozenset[str]:
    ids: set[str] = {fact.fact_id for fact in context.facts}
    ids |= {fact.fact_id for fact in context.warnings}
    for group in context.recommendation_facts:
        ids |= {fact.fact_id for fact in group}
    for group in context.tracking_facts:
        ids |= {fact.fact_id for fact in group}
    return frozenset(ids)


def _validate_narrative(
    *,
    narrative: ExplanationNarrative,
    context: ExplanationContext,
    recommendation_cards: tuple[RecommendationFactCard, ...],
    tracking_cards: tuple[TrackingFactCard, ...],
) -> bool:
    """Every cited fact ID must exist in the exact context sent; every
    recommendation/tracking explanation must match its card 1:1, in order,
    by ``trade_id`` (and ``family`` for recommendations) - no extra
    narrative, no missing narrative, no duplicate, no mismatch. An invalid
    result is never partially accepted."""
    known_ids = _all_context_fact_ids(context)
    for explanation in narrative.recommendation_explanations:
        if any(fact_id not in known_ids for fact_id in explanation.cited_fact_ids):
            return False
    for tracking_explanation in narrative.tracking_explanations:
        if any(fact_id not in known_ids for fact_id in tracking_explanation.cited_fact_ids):
            return False

    if len(narrative.recommendation_explanations) != len(recommendation_cards):
        return False
    for explanation, card in zip(narrative.recommendation_explanations, recommendation_cards):
        if explanation.trade_id != card.trade_id or explanation.family is not card.family:
            return False

    if len(narrative.tracking_explanations) != len(tracking_cards):
        return False
    for tracking_explanation, card in zip(narrative.tracking_explanations, tracking_cards):
        if tracking_explanation.trade_id != card.trade_id:
            return False

    return True


def _combine(
    narrative: ExplanationNarrative,
    recommendation_cards: tuple[RecommendationFactCard, ...],
    tracking_cards: tuple[TrackingFactCard, ...],
) -> ExplanationResult:
    return ExplanationResult(
        content_status=ExplanationContentStatus.AVAILABLE,
        provider_status=ExplanationProviderStatus.LLM_SUCCESS,
        headline=narrative.headline,
        cycle_summary=narrative.cycle_summary,
        recommendation_cards=recommendation_cards,
        recommendation_explanations=narrative.recommendation_explanations,
        tracking_cards=tracking_cards,
        tracking_explanations=narrative.tracking_explanations,
        no_trade_explanation=narrative.no_trade_explanation,
        warnings=narrative.warnings,
        data_quality_notes=narrative.data_quality_notes,
        risk_notes=narrative.risk_notes,
    )


# --- impure orchestration entry point ------------------------------------


def explain_runtime_cycle(*, result: RuntimeCycleResult, llm_client: ExplanationLLMClient) -> ExplanationResult:
    """The single impure entry point. Never modifies ``result``. At most one
    provider call plus at most one retry - retried only when the provider
    responded with structurally invalid output (``narrative`` present but
    failing validation, or ``narrative is None``); a raised exception from
    ``llm_client.explain`` is treated as provider-unavailable immediately,
    never retried."""
    recommendation_cards = build_recommendation_cards(result)
    tracking_cards = build_tracking_cards(result)
    context = build_explanation_context(result)

    def _attempt(previous_error: str | None) -> tuple[ExplanationNarrative | None, bool]:
        request = ExplanationRequest(context=context, previous_validation_error=previous_error)
        try:
            response: ExplanationLLMResponse = llm_client.explain(request)
        except Exception:
            return None, True
        if response.narrative is not None and _validate_narrative(
            narrative=response.narrative, context=context, recommendation_cards=recommendation_cards, tracking_cards=tracking_cards
        ):
            return response.narrative, False
        return None, False

    narrative, provider_unavailable = _attempt(None)
    if provider_unavailable:
        return render_deterministic_fallback(
            context=context,
            recommendation_cards=recommendation_cards,
            tracking_cards=tracking_cards,
            provider_status=ExplanationProviderStatus.LLM_UNAVAILABLE,
        )
    if narrative is not None:
        return _combine(narrative, recommendation_cards, tracking_cards)

    narrative, provider_unavailable = _attempt("previous structured output failed validation")
    if provider_unavailable:
        return render_deterministic_fallback(
            context=context,
            recommendation_cards=recommendation_cards,
            tracking_cards=tracking_cards,
            provider_status=ExplanationProviderStatus.LLM_UNAVAILABLE,
        )
    if narrative is not None:
        return _combine(narrative, recommendation_cards, tracking_cards)

    return render_deterministic_fallback(
        context=context,
        recommendation_cards=recommendation_cards,
        tracking_cards=tracking_cards,
        provider_status=ExplanationProviderStatus.LLM_INVALID_OUTPUT,
    )


__all__ = [
    "build_explanation_context",
    "build_recommendation_cards",
    "build_tracking_cards",
    "explain_runtime_cycle",
    "render_deterministic_fallback",
]
