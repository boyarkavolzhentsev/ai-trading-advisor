"""Deterministic Market Evaluator (Stage 5A).

Aggregates already-produced Flow/Technical/External-Intelligence supervisor
results for one explicit ``MarketEvaluationContext`` into one
``MarketEvaluationResult``: per-contour participation/quality, a
participation-derived top-level outcome, and structural (identity-only)
alignment of External Intelligence's heterogeneous native scopes against the
caller's explicit context. Never invokes a supervisor, never touches a
Flow/Technical/External analyst or foundation package, never performs I/O -
a pure, synchronous, stateless function of its input (see
``app.market_evaluation.protocols.MarketEvaluationProtocol``).

Unlike Flow/Technical/External's own supervisors, this evaluator has no
single shared identity anchor to validate every input against: Flow and
Technical each anchor to one ``(symbol, contract_type)`` instrument (checked
against the caller's ``MarketEvaluationContext``), while External
Intelligence carries no such anchor at all - its relevance to this context is
established scope-by-scope via exact identity matching only, never fuzzy
matching, normalization, aliasing, or symbol parsing.

The severity fold used to compute ``overall_quality`` is a tiny, locally-
owned copy - not imported from ``app.core.models.market_evaluation_result``
(whose own model validator independently re-derives the same fold to
self-validate its own field) and not imported from any Flow/Technical/
External Intelligence contour package. This mirrors the Stage 4G precedent
of the operational supervisor and the model's own self-validation
maintaining independent copies of the identical tiny primitive rather than
cross-importing one from the other.

Performs zero semantic cross-contour comparison: no Flow-vs-Technical
direction/momentum/structure comparison, no news-sentiment-vs-technical
comparison, no macro-vs-price comparison, no on-chain-vs-flow comparison, no
agreement/contradiction/coherence/confluence engine of any kind. Structural
scope alignment is exact identity matching against explicit context fields,
never an interpretation of what any contour's evidence says.
"""

from __future__ import annotations

from app.core.enums.external_intelligence_analysis import ExternalIntelligenceAnalystType
from app.core.enums.market_evaluation import (
    ExternalAlignmentStatus,
    ExternalScopeMatchKind,
    MarketEvaluationContourStatus,
    MarketEvaluationOutcome,
)
from app.core.enums.quality import FeatureQuality
from app.core.models.base import Timestamp
from app.core.models.external_intelligence_supervisor_result import ExternalIntelligenceSupervisorResult
from app.core.models.flow_supervisor_result import FlowSupervisorResult
from app.core.models.market_evaluation_context import MarketEvaluationContext
from app.core.models.market_evaluation_result import ExternalScopeAlignmentRef, MarketEvaluationResult
from app.core.models.technical_supervisor_result import TechnicalSupervisorResult
from app.market_evaluation.errors import FutureContourTimeError, ScopeMismatchError

_CURRENCY_SCOPED_ANALYST_TYPES = (
    ExternalIntelligenceAnalystType.MACRO_EVENT,
    ExternalIntelligenceAnalystType.RATES_YIELD,
)

_QUALIFYING_STATUSES = (MarketEvaluationContourStatus.ANALYZED, MarketEvaluationContourStatus.PARTIAL)

_QUALITY_SEVERITY: dict[FeatureQuality, int] = {
    FeatureQuality.VALID: 0,
    FeatureQuality.PARTIAL: 1,
    FeatureQuality.STALE: 2,
    FeatureQuality.UNAVAILABLE: 3,
}


def _worse_of_many(qualities: list[FeatureQuality]) -> FeatureQuality:
    result = FeatureQuality.VALID
    for quality in qualities:
        if _QUALITY_SEVERITY[quality] > _QUALITY_SEVERITY[result]:
            result = quality
    return result


def _contour_status(
    outcome_value: str | None,
) -> MarketEvaluationContourStatus:
    if outcome_value is None:
        return MarketEvaluationContourStatus.MISSING
    return MarketEvaluationContourStatus(outcome_value)


class MarketEvaluator:
    """Deterministic Stage 5A aggregator over Flow/Technical/External
    Intelligence supervisor results."""

    def evaluate(
        self,
        *,
        flow: FlowSupervisorResult | None,
        technical: TechnicalSupervisorResult | None,
        external: ExternalIntelligenceSupervisorResult | None,
        context: MarketEvaluationContext,
        evaluation_time: Timestamp,
    ) -> MarketEvaluationResult:
        if flow is not None:
            if flow.symbol != context.symbol or flow.contract_type != context.contract_type:
                raise ScopeMismatchError("flow result (symbol, contract_type) does not match context")
            if flow.observation_time > evaluation_time:
                raise FutureContourTimeError("flow.observation_time is after evaluation_time")

        if technical is not None:
            if technical.symbol != context.symbol or technical.contract_type != context.contract_type:
                raise ScopeMismatchError("technical result (symbol, contract_type) does not match context")
            if technical.observation_time > evaluation_time:
                raise FutureContourTimeError("technical.observation_time is after evaluation_time")

        if external is not None and external.analysis_time > evaluation_time:
            raise FutureContourTimeError("external.analysis_time is after evaluation_time")

        flow_status = _contour_status(flow.outcome.value if flow is not None else None)
        technical_status = _contour_status(technical.outcome.value if technical is not None else None)
        external_status = _contour_status(external.outcome.value if external is not None else None)

        flow_quality = flow.overall_quality if flow is not None else None
        technical_quality = technical.overall_quality if technical is not None else None
        external_quality = external.overall_quality if external is not None else None

        statuses = (flow_status, technical_status, external_status)
        if all(status is MarketEvaluationContourStatus.ANALYZED for status in statuses):
            outcome = MarketEvaluationOutcome.EVALUATED
        elif any(status in _QUALIFYING_STATUSES for status in statuses):
            outcome = MarketEvaluationOutcome.PARTIAL
        else:
            outcome = MarketEvaluationOutcome.INSUFFICIENT_EVIDENCE

        qualifying_qualities = [
            quality
            for status, quality in (
                (flow_status, flow_quality),
                (technical_status, technical_quality),
                (external_status, external_quality),
            )
            if status in _QUALIFYING_STATUSES and quality is not None
        ]
        overall_quality = _worse_of_many(qualifying_qualities) if qualifying_qualities else FeatureQuality.UNAVAILABLE

        alignment_refs = self._align_external_scopes(external, context)
        if external is None:
            alignment_status = ExternalAlignmentStatus.MISSING
        elif alignment_refs:
            alignment_status = ExternalAlignmentStatus.MATCHED
        else:
            alignment_status = ExternalAlignmentStatus.NO_MATCHING_SCOPE

        return MarketEvaluationResult(
            evaluation_time=evaluation_time,
            context=context,
            outcome=outcome,
            flow_status=flow_status,
            technical_status=technical_status,
            external_status=external_status,
            flow_quality=flow_quality,
            technical_quality=technical_quality,
            external_quality=external_quality,
            overall_quality=overall_quality,
            flow=flow,
            technical=technical,
            external=external,
            external_alignment_status=alignment_status,
            external_scope_alignment=alignment_refs,
        )

    @staticmethod
    def _align_external_scopes(
        external: ExternalIntelligenceSupervisorResult | None,
        context: MarketEvaluationContext,
    ) -> tuple[ExternalScopeAlignmentRef, ...]:
        if external is None:
            return ()

        refs: list[ExternalScopeAlignmentRef] = []
        for index, scope in enumerate(external.scope_summaries):
            if scope.analyst_type is ExternalIntelligenceAnalystType.NEWS_SENTIMENT:
                if scope.symbol == context.symbol:
                    refs.append(
                        ExternalScopeAlignmentRef(scope_summary_index=index, matched_by=ExternalScopeMatchKind.SYMBOL)
                    )
            elif scope.analyst_type is ExternalIntelligenceAnalystType.ON_CHAIN:
                if (
                    context.base_asset is not None
                    and context.network is not None
                    and scope.asset == context.base_asset
                    and scope.network == context.network
                ):
                    refs.append(
                        ExternalScopeAlignmentRef(
                            scope_summary_index=index, matched_by=ExternalScopeMatchKind.ASSET_NETWORK
                        )
                    )
            elif scope.analyst_type in _CURRENCY_SCOPED_ANALYST_TYPES:
                if scope.currency in context.currency_exposures:
                    refs.append(
                        ExternalScopeAlignmentRef(scope_summary_index=index, matched_by=ExternalScopeMatchKind.CURRENCY)
                    )
        return tuple(refs)


__all__ = ["MarketEvaluator"]
