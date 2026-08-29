"""Deterministic External Intelligence Supervisor (Stage 4G).

Aggregates already-produced Stage 4F ``ExternalIntelligenceAnalysisResult``
objects for one analysis pass into one ``ExternalIntelligenceSupervisorResult``:
which analyst *types* produced usable evidence, which abstained, which are
missing, what evidence quality resulted, and a plain index back into the
embedded results for traceability. Never invokes an analyst, never touches
Stage 4A-4E facts directly, never performs I/O - a pure, synchronous,
stateless function of its input sequence and an explicit ``analysis_time``
(see ``app.external_intelligence_supervisor.protocols.ExternalIntelligenceSupervisorProtocol``).

Unlike ``FlowSupervisor``/``TechnicalSupervisor``, this supervisor has no
single shared identity anchor to validate embedded results against: Stage 4F
results are scoped per analyst type (``currency`` for Macro/Rates, ``symbol``
for News, ``asset``+``network`` for On-Chain), so identity here is
``(analyst_type, native_scope)`` rather than one shared snapshot key. Reuses
``app.external_intelligence_analysts.base.worse_of_many`` rather than
reimplementing it - Stage 4F's own audited, provider-agnostic quality-fold
primitive, not a new dependency edge into a different contour.

Deliberately does not read, interpret, or promote any individual
``ExternalIntelligenceDimension`` value (no ``SENTIMENT_PROVIDER_AGREEMENT``
promotion, no contradiction/agreement/coherence subsystem, no cross-domain
mapping or weighting): every Stage 4F observation remains reachable only
through the unchanged, embedded ``analysis_results`` tuple. See the approved
Stage 4G design report for the full boundary this module enforces.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.core.enums.external_intelligence_analysis import ExternalIntelligenceAnalystType, ExternalIntelligenceOutcome
from app.core.enums.external_intelligence_supervisor import ExternalIntelligenceSupervisorOutcome
from app.core.enums.quality import FeatureQuality
from app.core.models.base import Timestamp
from app.core.models.external_intelligence_analysis_result import ExternalIntelligenceAnalysisResult
from app.core.models.external_intelligence_supervisor_result import (
    ExternalIntelligenceScopeSummary,
    ExternalIntelligenceSupervisorResult,
)
from app.external_intelligence_analysts.base import worse_of_many
from app.external_intelligence_supervisor.errors import (
    DuplicateAnalystScopeResultError,
    ExternalIntelligenceSupervisorInputError,
    FutureResultTimeError,
)

DEFAULT_EXPECTED_ANALYSTS: tuple[ExternalIntelligenceAnalystType, ...] = tuple(ExternalIntelligenceAnalystType)
"""Explicit, deterministic default expected-analyst-type set: all four approved Stage 4F specialists."""

_CANONICAL_ORDER: tuple[ExternalIntelligenceAnalystType, ...] = tuple(ExternalIntelligenceAnalystType)
"""Fixed sort key for every analyst-type tuple this module emits (enum declaration order)."""

_CURRENCY_SCOPED: tuple[ExternalIntelligenceAnalystType, ...] = (
    ExternalIntelligenceAnalystType.MACRO_EVENT,
    ExternalIntelligenceAnalystType.RATES_YIELD,
)

Identity = tuple[ExternalIntelligenceAnalystType, tuple[str | None, ...]]


def _canonical_key(analyst_type: ExternalIntelligenceAnalystType) -> int:
    return _CANONICAL_ORDER.index(analyst_type)


def _native_scope(result: ExternalIntelligenceAnalysisResult) -> tuple[str | None, ...]:
    """The analyst-appropriate native scope tuple for one result - exactly
    mirrors ``ExternalIntelligenceAnalysisResult``'s own scope-shape
    validator (``app.core.models.external_intelligence_analysis_result``)."""
    if result.analyst_type in _CURRENCY_SCOPED:
        return (result.currency,)
    if result.analyst_type is ExternalIntelligenceAnalystType.NEWS_SENTIMENT:
        return (result.symbol,)
    return (result.asset, result.network)


def _scope_sort_key(scope: tuple[str | None, ...]) -> tuple[str, ...]:
    return tuple(part or "" for part in scope)


class ExternalIntelligenceSupervisor:
    """Deterministic Stage 4G aggregator over Stage 4F analyst results."""

    def __init__(
        self, expected_analysts: tuple[ExternalIntelligenceAnalystType, ...] = DEFAULT_EXPECTED_ANALYSTS
    ) -> None:
        if not expected_analysts:
            raise ExternalIntelligenceSupervisorInputError("expected_analysts must not be empty")
        if len(set(expected_analysts)) != len(expected_analysts):
            raise ExternalIntelligenceSupervisorInputError(
                "expected_analysts must not contain duplicate ExternalIntelligenceAnalystType entries"
            )
        self._expected_analysts = tuple(sorted(expected_analysts, key=_canonical_key))

    @property
    def expected_analysts(self) -> tuple[ExternalIntelligenceAnalystType, ...]:
        return self._expected_analysts

    def aggregate(
        self,
        results: Sequence[ExternalIntelligenceAnalysisResult],
        *,
        analysis_time: Timestamp,
    ) -> ExternalIntelligenceSupervisorResult:
        by_identity: dict[Identity, ExternalIntelligenceAnalysisResult] = {}
        for result in results:
            if result.analysis_time > analysis_time:
                raise FutureResultTimeError(
                    f"result for {result.analyst_type} has analysis_time {result.analysis_time} "
                    f"after supervisor analysis_time {analysis_time}"
                )
            identity: Identity = (result.analyst_type, _native_scope(result))
            if identity in by_identity:
                raise DuplicateAnalystScopeResultError(f"duplicate result for identity {identity}")
            by_identity[identity] = result

        canonical_identities = sorted(
            by_identity, key=lambda identity: (_canonical_key(identity[0]), _scope_sort_key(identity[1]))
        )
        analysis_results = tuple(by_identity[identity] for identity in canonical_identities)

        scope_summaries = tuple(
            ExternalIntelligenceScopeSummary(
                analyst_type=result.analyst_type,
                currency=result.currency,
                symbol=result.symbol,
                asset=result.asset,
                network=result.network,
                result_outcome=result.status,
                quality=result.quality,
                result_index=idx,
            )
            for idx, result in enumerate(analysis_results)
        )

        types_with_result = {result.analyst_type for result in analysis_results}
        types_analyzed = {
            result.analyst_type for result in analysis_results if result.status is ExternalIntelligenceOutcome.ANALYZED
        }

        analyzed = tuple(t for t in self._expected_analysts if t in types_analyzed)
        abstained = tuple(t for t in self._expected_analysts if t in types_with_result and t not in types_analyzed)
        missing = tuple(t for t in self._expected_analysts if t not in types_with_result)

        expected_count = len(self._expected_analysts)
        analyzed_count = len(analyzed)

        if analyzed_count == 0:
            outcome = ExternalIntelligenceSupervisorOutcome.INSUFFICIENT_EVIDENCE
        elif analyzed_count == expected_count:
            outcome = ExternalIntelligenceSupervisorOutcome.ANALYZED
        else:
            outcome = ExternalIntelligenceSupervisorOutcome.PARTIAL

        analyzed_results = tuple(r for r in analysis_results if r.status is ExternalIntelligenceOutcome.ANALYZED)
        abstained_results = tuple(r for r in analysis_results if r.status is ExternalIntelligenceOutcome.ABSTAINED)

        overall_quality = (
            worse_of_many([r.quality for r in analyzed_results]) if analyzed_results else FeatureQuality.UNAVAILABLE
        )

        return ExternalIntelligenceSupervisorResult(
            analysis_time=analysis_time,
            outcome=outcome,
            expected_analyst_types=self._expected_analysts,
            analyzed_analyst_types=analyzed,
            abstained_analyst_types=abstained,
            missing_analyst_types=missing,
            total_input_results=len(analysis_results),
            total_analyzed_results=len(analyzed_results),
            total_abstained_results=len(abstained_results),
            overall_quality=overall_quality,
            scope_summaries=scope_summaries,
            analysis_results=analysis_results,
        )


__all__ = ["DEFAULT_EXPECTED_ANALYSTS", "ExternalIntelligenceSupervisor"]
