"""Deterministic Judge (Stage 6B).

Interprets semantic dimension/value content for every Router-eligible
``StrategyFamily`` only - Router-ineligible families never produce a
``JudgeFamilyResult``. Each family's evidence rule is its own narrow,
hand-justified function (see the approved Stage 6B design report); there is
deliberately no shared, generic "positive/negative -> direction" engine
spanning contours - every mapping dict below is keyed to one specific
upstream enum's ``.value`` strings, chosen individually per family/dimension.

Reads Technical evidence via ``TechnicalSupervisorResult.coherence`` (Stage
3C's own pre-computed cross-timeframe ``ALL_AGREE``/``MIXED``/
``INSUFFICIENT_DATA`` tally) wherever an entry exists for the needed
dimension, mirroring ``TechnicalCoherenceResult.evidence_refs``'s own
``(result_index, observation_index)`` shape - never re-deriving cross-
timeframe agreement itself. ``STRUCTURAL_BREAK_PRESENCE`` has no coherence
entry (Stage 3C never computes one for it), so it is read directly from
``analyst_results``.

Flow dimensions are never read: no explicit contract ties a
``FlowSupervisorResult`` window to a ``TechnicalSupervisorResult`` timeframe,
so Flow's structural presence (required by Router for ``BREAKOUT``) has zero
effect on any Judge verdict in V1 - this is intentional, not an oversight.
Only ``NEWS_SENTIMENT`` is read from External Intelligence; MACRO_EVENT,
RATES_YIELD (blocked by the missing currency base/quote role on
``MarketEvaluationContext``) and ON_CHAIN (blocked by inherent semantic
ambiguity, per ``OnChainAnalyst``'s own docstring) are never interpreted for
direction. ``MEAN_REVERSION`` has no defined primary evidence in V1 at all -
current Technical contracts never expose a genuine, non-arbitrary
overextension/reversal trigger (see the approved design report) - so it
always abstains.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.enums.external_intelligence_analysis import (
    ExternalIntelligenceAnalystType,
    ExternalIntelligenceDimension,
    SentimentAgreementVerdict,
    SentimentSign,
)
from app.core.enums.market_evaluation import ExternalScopeMatchKind
from app.core.enums.strategy_judge import DirectionalCandidate, EvidenceRole, JudgeContour, JudgeOutcome
from app.core.enums.strategy_router import StrategyFamily
from app.core.enums.technical import BreakDirection
from app.core.enums.technical_analysis import (
    MidpointRelation,
    MovingAverageSlopeDirection,
    MultiPeriodMAOrdering,
    StructuralBreakPresence,
    StructuralSequenceBalance,
    TechnicalAgreementVerdict,
    TechnicalAnalysisDimension,
    TechnicalAnalystType,
    PricePositionRelativeToMA,
    TrendDirection,
)
from app.core.models.external_intelligence_supervisor_result import ExternalIntelligenceSupervisorResult
from app.core.models.market_evaluation_result import MarketEvaluationResult
from app.core.models.strategy_judge_result import JudgeEvidenceRef, JudgeFamilyResult, StrategyJudgeResult
from app.core.models.strategy_router_result import StrategyRouterResult
from app.core.models.technical_supervisor_result import TechnicalCoherenceResult, TechnicalSupervisorResult

_CONTOUR_ORDER = tuple(JudgeContour)
_ROLE_ORDER = tuple(EvidenceRole)

# Per-dimension mapping tables. Each is deliberately private, small, and
# keyed to exactly one upstream enum's own ``.value`` strings - never a
# shared cross-contour "sign -> direction" table. A value absent from a
# mapping (e.g. ``TrendDirection.FLAT``) has no directional reading.
_TREND_DIRECTION_MAP: dict[str, DirectionalCandidate] = {
    TrendDirection.UPWARD.value: DirectionalCandidate.LONG_CANDIDATE,
    TrendDirection.DOWNWARD.value: DirectionalCandidate.SHORT_CANDIDATE,
}
_BREAK_DIRECTION_MAP: dict[str, DirectionalCandidate] = {
    BreakDirection.UPWARD_BREAK.value: DirectionalCandidate.LONG_CANDIDATE,
    BreakDirection.DOWNWARD_BREAK.value: DirectionalCandidate.SHORT_CANDIDATE,
}
_PRICE_VS_SMA_MAP: dict[str, DirectionalCandidate] = {
    PricePositionRelativeToMA.ABOVE_SMA.value: DirectionalCandidate.LONG_CANDIDATE,
    PricePositionRelativeToMA.BELOW_SMA.value: DirectionalCandidate.SHORT_CANDIDATE,
}
_MA_SLOPE_MAP: dict[str, DirectionalCandidate] = {
    MovingAverageSlopeDirection.UPWARD.value: DirectionalCandidate.LONG_CANDIDATE,
    MovingAverageSlopeDirection.DOWNWARD.value: DirectionalCandidate.SHORT_CANDIDATE,
}
_MULTI_PERIOD_MA_MAP: dict[str, DirectionalCandidate] = {
    MultiPeriodMAOrdering.FASTER_ABOVE_SLOWER.value: DirectionalCandidate.LONG_CANDIDATE,
    MultiPeriodMAOrdering.FASTER_BELOW_SLOWER.value: DirectionalCandidate.SHORT_CANDIDATE,
}
_STRUCTURAL_SEQUENCE_MAP: dict[str, DirectionalCandidate] = {
    StructuralSequenceBalance.UPWARD_STRUCTURE.value: DirectionalCandidate.LONG_CANDIDATE,
    StructuralSequenceBalance.DOWNWARD_STRUCTURE.value: DirectionalCandidate.SHORT_CANDIDATE,
}
_RSI_MIDPOINT_MAP: dict[str, DirectionalCandidate] = {
    MidpointRelation.ABOVE_MIDPOINT.value: DirectionalCandidate.LONG_CANDIDATE,
    MidpointRelation.BELOW_MIDPOINT.value: DirectionalCandidate.SHORT_CANDIDATE,
}
_SENTIMENT_MAP: dict[str, DirectionalCandidate] = {
    SentimentSign.POSITIVE.value: DirectionalCandidate.LONG_CANDIDATE,
    SentimentSign.NEGATIVE.value: DirectionalCandidate.SHORT_CANDIDATE,
}

_TREND_FOLLOWING_CORROBORATORS: tuple[tuple[TechnicalAnalysisDimension, dict[str, DirectionalCandidate]], ...] = (
    (TechnicalAnalysisDimension.PRICE_VS_SMA_POSITION, _PRICE_VS_SMA_MAP),
    (TechnicalAnalysisDimension.MA_SLOPE_DIRECTION, _MA_SLOPE_MAP),
    (TechnicalAnalysisDimension.MULTI_PERIOD_MA_ORDERING, _MULTI_PERIOD_MA_MAP),
    (TechnicalAnalysisDimension.STRUCTURAL_SEQUENCE_BALANCE, _STRUCTURAL_SEQUENCE_MAP),
    (TechnicalAnalysisDimension.RSI_MIDPOINT_RELATION, _RSI_MIDPOINT_MAP),
)


@dataclass(frozen=True, slots=True)
class _Resolved:
    """Internal-only resolution of one dimension's coherence/agreement entry."""

    conflict: bool
    candidate: DirectionalCandidate | None
    refs: tuple[JudgeEvidenceRef, ...]


_UNRESOLVED = _Resolved(conflict=False, candidate=None, refs=())


def _canonicalize(refs: tuple[JudgeEvidenceRef, ...]) -> tuple[JudgeEvidenceRef, ...]:
    unique = {
        (_CONTOUR_ORDER.index(ref.contour), _ROLE_ORDER.index(ref.role), ref.analyst_result_index, ref.observation_index): ref
        for ref in refs
    }
    return tuple(unique[key] for key in sorted(unique))


def _find_coherence_entries(
    technical: TechnicalSupervisorResult, dimension: TechnicalAnalysisDimension
) -> tuple[TechnicalCoherenceResult, ...]:
    return tuple(entry for entry in technical.coherence if entry.dimension is dimension)


def _resolve_coherence_entry(
    entry: TechnicalCoherenceResult,
    technical: TechnicalSupervisorResult,
    mapping: dict[str, DirectionalCandidate],
    role: EvidenceRole,
) -> _Resolved:
    if entry.verdict is TechnicalAgreementVerdict.MIXED:
        refs = tuple(
            JudgeEvidenceRef(contour=JudgeContour.TECHNICAL, role=role, analyst_result_index=i, observation_index=j)
            for i, j in entry.evidence_refs
        )
        return _Resolved(conflict=True, candidate=None, refs=refs)
    if entry.verdict is TechnicalAgreementVerdict.INSUFFICIENT_DATA:
        return _UNRESOLVED

    # ALL_AGREE: every referenced observation shares the same value.
    result_index, observation_index = entry.evidence_refs[0]
    value = technical.analyst_results[result_index].observations[observation_index].value
    candidate = mapping.get(value)
    if candidate is None:
        return _UNRESOLVED
    refs = tuple(
        JudgeEvidenceRef(contour=JudgeContour.TECHNICAL, role=role, analyst_result_index=i, observation_index=j)
        for i, j in entry.evidence_refs
    )
    return _Resolved(conflict=False, candidate=candidate, refs=refs)


def _resolve_single_dimension(
    technical: TechnicalSupervisorResult,
    dimension: TechnicalAnalysisDimension,
    mapping: dict[str, DirectionalCandidate],
    role: EvidenceRole,
) -> _Resolved:
    """For dimensions with at most one (subject-less) coherence entry."""
    entries = _find_coherence_entries(technical, dimension)
    if not entries:
        return _UNRESOLVED
    return _resolve_coherence_entry(entries[0], technical, mapping, role)


def _corroborating_veto_refs(
    technical: TechnicalSupervisorResult, primary_direction: DirectionalCandidate
) -> tuple[JudgeEvidenceRef, ...]:
    """Only a corroborator resolving to a *concrete opposite* candidate
    vetoes. An internally ambiguous (``MIXED``) or unusable
    (``INSUFFICIENT_DATA``) corroborator is silent - unlike a family's own
    PRIMARY dimensions, it has nothing clear to veto with."""
    vetoes: list[JudgeEvidenceRef] = []
    for dimension, mapping in _TREND_FOLLOWING_CORROBORATORS:
        for entry in _find_coherence_entries(technical, dimension):
            resolved = _resolve_coherence_entry(entry, technical, mapping, EvidenceRole.CORROBORATING)
            if resolved.candidate is not None and resolved.candidate is not primary_direction:
                vetoes.extend(resolved.refs)
    return tuple(vetoes)


def _judge_trend_following(
    technical: TechnicalSupervisorResult | None,
) -> tuple[JudgeOutcome, DirectionalCandidate | None, tuple[JudgeEvidenceRef, ...]]:
    if technical is None:
        return JudgeOutcome.INSUFFICIENT_EVIDENCE, None, ()

    # An internally MIXED coherence verdict on a PRIMARY dimension (i.e.
    # different timeframes disagree on that dimension's own sign) is itself
    # treated as demonstrated PRIMARY-vs-PRIMARY conflict - the safer,
    # conservative reading, rather than silently falling back to the other
    # primary dimension alone.
    return_resolved = _resolve_single_dimension(
        technical, TechnicalAnalysisDimension.RETURN_DIRECTION, _TREND_DIRECTION_MAP, EvidenceRole.PRIMARY
    )
    if return_resolved.conflict:
        return JudgeOutcome.MIXED, None, _canonicalize(return_resolved.refs)

    slope_resolved = _resolve_single_dimension(
        technical, TechnicalAnalysisDimension.SLOPE_DIRECTION, _TREND_DIRECTION_MAP, EvidenceRole.PRIMARY
    )
    if slope_resolved.conflict:
        return JudgeOutcome.MIXED, None, _canonicalize(slope_resolved.refs)

    primary_candidates = [r.candidate for r in (return_resolved, slope_resolved) if r.candidate is not None]
    primary_refs = tuple(ref for r in (return_resolved, slope_resolved) if r.candidate is not None for ref in r.refs)

    if not primary_candidates:
        return JudgeOutcome.INSUFFICIENT_EVIDENCE, None, ()

    if len(set(primary_candidates)) > 1:
        return JudgeOutcome.MIXED, None, _canonicalize(primary_refs)

    direction = primary_candidates[0]
    veto_refs = _corroborating_veto_refs(technical, direction)
    if veto_refs:
        return JudgeOutcome.MIXED, None, _canonicalize(primary_refs + veto_refs)

    return JudgeOutcome.DIRECTIONAL, direction, _canonicalize(primary_refs)


def _judge_mean_reversion() -> tuple[JudgeOutcome, DirectionalCandidate | None, tuple[JudgeEvidenceRef, ...]]:
    """No dimension in the current Technical contour is a genuine, non-
    arbitrary overextension/reversal trigger (RSI-midpoint, price-vs-SMA,
    range/chop state, and candle geometry are all sign/boundary-only, never
    a calibrated extremity threshold) - this family always abstains in V1."""
    return JudgeOutcome.INSUFFICIENT_EVIDENCE, None, ()


def _structural_break_confirmed_refs(technical: TechnicalSupervisorResult) -> tuple[JudgeEvidenceRef, ...]:
    refs: list[JudgeEvidenceRef] = []
    for result_index, result in enumerate(technical.analyst_results):
        if result.analyst_type is not TechnicalAnalystType.MARKET_STRUCTURE:
            continue
        for observation_index, observation in enumerate(result.observations):
            if (
                observation.dimension is TechnicalAnalysisDimension.STRUCTURAL_BREAK_PRESENCE
                and observation.value == StructuralBreakPresence.BREAK_CONFIRMED.value
            ):
                refs.append(
                    JudgeEvidenceRef(
                        contour=JudgeContour.TECHNICAL,
                        role=EvidenceRole.PRIMARY,
                        analyst_result_index=result_index,
                        observation_index=observation_index,
                    )
                )
    return tuple(refs)


def _judge_breakout(
    technical: TechnicalSupervisorResult | None,
) -> tuple[JudgeOutcome, DirectionalCandidate | None, tuple[JudgeEvidenceRef, ...]]:
    if technical is None:
        return JudgeOutcome.INSUFFICIENT_EVIDENCE, None, ()

    confirmed_refs = _structural_break_confirmed_refs(technical)

    latest_resolved = _resolve_single_dimension(
        technical, TechnicalAnalysisDimension.LATEST_BREAK_DIRECTION, _BREAK_DIRECTION_MAP, EvidenceRole.PRIMARY
    )
    if latest_resolved.conflict:
        return JudgeOutcome.MIXED, None, _canonicalize(latest_resolved.refs)

    if not confirmed_refs or latest_resolved.candidate is None:
        return JudgeOutcome.INSUFFICIENT_EVIDENCE, None, ()

    direction = latest_resolved.candidate
    primary_refs = confirmed_refs + latest_resolved.refs

    return_resolved = _resolve_single_dimension(
        technical, TechnicalAnalysisDimension.RETURN_DIRECTION, _TREND_DIRECTION_MAP, EvidenceRole.CORROBORATING
    )
    if return_resolved.candidate is not None and return_resolved.candidate is not direction:
        return JudgeOutcome.MIXED, None, _canonicalize(primary_refs + return_resolved.refs)

    return JudgeOutcome.DIRECTIONAL, direction, _canonicalize(primary_refs)


def _aligned_news_sentiment_result_indices(market_evaluation: MarketEvaluationResult) -> tuple[int, ...]:
    external = market_evaluation.external
    if external is None:
        return ()
    indices: set[int] = set()
    for ref in market_evaluation.external_scope_alignment:
        if ref.matched_by is not ExternalScopeMatchKind.SYMBOL:
            continue
        scope = external.scope_summaries[ref.scope_summary_index]
        if scope.analyst_type is ExternalIntelligenceAnalystType.NEWS_SENTIMENT:
            indices.add(scope.result_index)
    return tuple(sorted(indices))


def _resolve_news_sentiment_result(external: ExternalIntelligenceSupervisorResult, result_index: int) -> _Resolved:
    result = external.analysis_results[result_index]

    agreement_value: str | None = None
    for observation in result.observations:
        if observation.dimension is ExternalIntelligenceDimension.SENTIMENT_PROVIDER_AGREEMENT:
            agreement_value = observation.value
            break
    if agreement_value is None:
        return _UNRESOLVED

    if agreement_value == SentimentAgreementVerdict.MIXED.value:
        refs = tuple(
            JudgeEvidenceRef(
                contour=JudgeContour.EXTERNAL,
                role=EvidenceRole.PRIMARY,
                analyst_result_index=result_index,
                observation_index=idx,
            )
            for idx, observation in enumerate(result.observations)
            if observation.dimension is ExternalIntelligenceDimension.PER_PROVIDER_SENTIMENT_SIGN
            and observation.value in (SentimentSign.POSITIVE.value, SentimentSign.NEGATIVE.value)
        )
        return _Resolved(conflict=True, candidate=None, refs=refs)

    if agreement_value != SentimentAgreementVerdict.ALL_AGREE.value:
        return _UNRESOLVED

    for observation in result.observations:
        if observation.dimension is not ExternalIntelligenceDimension.PER_PROVIDER_SENTIMENT_SIGN:
            continue
        candidate = _SENTIMENT_MAP.get(observation.value)
        if candidate is None:
            continue
        refs = tuple(
            JudgeEvidenceRef(
                contour=JudgeContour.EXTERNAL,
                role=EvidenceRole.PRIMARY,
                analyst_result_index=result_index,
                observation_index=idx,
            )
            for idx, obs in enumerate(result.observations)
            if obs.dimension is ExternalIntelligenceDimension.PER_PROVIDER_SENTIMENT_SIGN and obs.value == observation.value
        )
        return _Resolved(conflict=False, candidate=candidate, refs=refs)

    return _UNRESOLVED


def _judge_event_driven(
    market_evaluation: MarketEvaluationResult,
) -> tuple[JudgeOutcome, DirectionalCandidate | None, tuple[JudgeEvidenceRef, ...]]:
    external = market_evaluation.external
    if external is None:
        return JudgeOutcome.INSUFFICIENT_EVIDENCE, None, ()

    result_indices = _aligned_news_sentiment_result_indices(market_evaluation)
    if not result_indices:
        return JudgeOutcome.INSUFFICIENT_EVIDENCE, None, ()

    resolved_list = [_resolve_news_sentiment_result(external, index) for index in result_indices]

    for resolved in resolved_list:
        if resolved.conflict:
            return JudgeOutcome.MIXED, None, _canonicalize(resolved.refs)

    candidates = [r.candidate for r in resolved_list if r.candidate is not None]
    refs = tuple(ref for r in resolved_list if r.candidate is not None for ref in r.refs)

    if not candidates:
        return JudgeOutcome.INSUFFICIENT_EVIDENCE, None, ()

    if len(set(candidates)) > 1:
        return JudgeOutcome.MIXED, None, _canonicalize(refs)

    return JudgeOutcome.DIRECTIONAL, candidates[0], _canonicalize(refs)


class Judge:
    """Deterministic Stage 6B judge over one ``StrategyRouterResult``."""

    def judge(self, *, strategy_router_result: StrategyRouterResult) -> StrategyJudgeResult:
        market_evaluation = strategy_router_result.market_evaluation
        family_results: list[JudgeFamilyResult] = []

        for family in strategy_router_result.eligible_families:
            if family is StrategyFamily.TREND_FOLLOWING:
                outcome, direction, refs = _judge_trend_following(market_evaluation.technical)
            elif family is StrategyFamily.MEAN_REVERSION:
                outcome, direction, refs = _judge_mean_reversion()
            elif family is StrategyFamily.BREAKOUT:
                outcome, direction, refs = _judge_breakout(market_evaluation.technical)
            elif family is StrategyFamily.EVENT_DRIVEN:
                outcome, direction, refs = _judge_event_driven(market_evaluation)
            else:
                raise AssertionError(f"unhandled StrategyFamily {family!r}")

            family_results.append(JudgeFamilyResult(family=family, outcome=outcome, direction=direction, evidence_refs=refs))

        return StrategyJudgeResult(
            strategy_router_result=strategy_router_result,
            family_results=tuple(family_results),
        )


__all__ = ["Judge"]
