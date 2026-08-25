"""Deterministic Flow Supervisor (Stage 2C).

Aggregates already-produced Stage 2B ``FlowAnalysisResult`` objects for one
snapshot. Never invokes an analyst, never touches a ``FlowFeatureSnapshot``,
never performs I/O - a pure, synchronous, stateless function of its input
sequence (see ``app.flow_supervisor.protocols.FlowSupervisorProtocol``).

Reuses ``app.flow_analysts.base.agreement_of``/``worse_of_many`` rather than
reimplementing them: these are narrow, provider-agnostic, already-audited
primitives shared with Stage 2B, not a dependency on any concrete analyst
implementation.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.core.enums.flow_analysis import AgreementVerdict, AnalysisDimension, AnalystOutcome, AnalystType
from app.core.enums.flow_supervisor import FlowSupervisorOutcome
from app.core.enums.quality import FeatureQuality
from app.core.models.flow_analysis_result import FlowAnalysisResult
from app.core.models.flow_supervisor_result import FlowSupervisorResult
from app.flow_analysts.base import agreement_of, worse_of_many
from app.flow_supervisor.errors import (
    DuplicateAnalystResultError,
    EmptyResultsError,
    FlowSupervisorInputError,
    InconsistentSnapshotError,
    UnexpectedAnalystResultError,
)

DEFAULT_EXPECTED_ANALYSTS: tuple[AnalystType, ...] = (
    AnalystType.TAKER_FLOW,
    AnalystType.LIQUIDATION,
    AnalystType.ORDER_BOOK_LIQUIDITY,
    AnalystType.OPEN_INTEREST,
    AnalystType.FUNDING,
    AnalystType.PRICE_FLOW_RELATIONSHIP,
)
"""Explicit, deterministic default expected-analyst set: the six Stage 2B specialists."""

_CANONICAL_ORDER: tuple[AnalystType, ...] = tuple(AnalystType)
"""Fixed sort key for every analyst-type tuple this module emits (enum declaration order)."""

_RELATIONSHIP_DIMENSIONS: tuple[AnalysisDimension, ...] = (
    AnalysisDimension.PRICE_TAKER_RELATIONSHIP,
    AnalysisDimension.PRICE_OPEN_INTEREST_RELATIONSHIP,
    AnalysisDimension.PRICE_LIQUIDATION_RELATIONSHIP,
)
"""The only dimensions that share one literal vocabulary (PriceFlowRelationship)
across independent flow domains - see FlowSupervisor's module docstring and
the approved Stage 2C design report, section 15-16, for why every other
same-named dimension across analysts is NOT safely comparable."""


def _canonical_key(analyst_type: AnalystType) -> int:
    return _CANONICAL_ORDER.index(analyst_type)


def _relationship_coherence(
    analyst_results: tuple[FlowAnalysisResult, ...],
) -> tuple[AgreementVerdict, tuple[tuple[int, int], ...]]:
    """Two-tier cross-domain relationship tally.

    Tier 1: each of the three PRICE_*_RELATIONSHIP dimensions is tallied
    independently across its own windows via ``agreement_of``. A dimension
    that is internally MIXED, or has fewer than 2 qualifying observations,
    contributes no vote - never fabricated, never averaged.

    Tier 2: one representative value per Tier-1 ALL_AGREE dimension is
    compared against every other representative. Each domain contributes at
    most one vote regardless of how many windows it has, so a domain with
    more windows never gains implicit extra weight.
    """
    relationship_result = next(
        (r for r in analyst_results if r.analyst_type is AnalystType.PRICE_FLOW_RELATIONSHIP),
        None,
    )
    if relationship_result is None:
        return AgreementVerdict.INSUFFICIENT_DATA, ()

    analyst_index = analyst_results.index(relationship_result)
    representative_values: list[str] = []
    representative_refs: list[tuple[int, int]] = []

    for dimension in _RELATIONSHIP_DIMENSIONS:
        obs_indices = [
            idx for idx, obs in enumerate(relationship_result.observations) if obs.dimension is dimension
        ]
        if not obs_indices:
            continue

        values = [relationship_result.observations[idx].value for idx in obs_indices]
        if agreement_of(values) is not AgreementVerdict.ALL_AGREE:
            continue

        representative_values.append(values[0])
        representative_refs.extend((analyst_index, idx) for idx in obs_indices)

    if len(representative_values) < 2:
        return AgreementVerdict.INSUFFICIENT_DATA, ()

    tier2 = AgreementVerdict.ALL_AGREE if len(set(representative_values)) == 1 else AgreementVerdict.MIXED
    return tier2, tuple(representative_refs)


class FlowSupervisor:
    """Deterministic Stage 2C aggregator over Stage 2B analyst results."""

    def __init__(self, expected_analysts: tuple[AnalystType, ...] = DEFAULT_EXPECTED_ANALYSTS) -> None:
        if not expected_analysts:
            raise FlowSupervisorInputError("expected_analysts must not be empty")
        if len(set(expected_analysts)) != len(expected_analysts):
            raise FlowSupervisorInputError("expected_analysts must not contain duplicate AnalystType entries")
        self._expected_analysts = tuple(sorted(expected_analysts, key=_canonical_key))

    @property
    def expected_analysts(self) -> tuple[AnalystType, ...]:
        return self._expected_analysts

    def aggregate(self, results: Sequence[FlowAnalysisResult]) -> FlowSupervisorResult:
        if not results:
            raise EmptyResultsError("aggregate requires at least one FlowAnalysisResult")

        by_type: dict[AnalystType, FlowAnalysisResult] = {}
        for result in results:
            if result.analyst_type in by_type:
                raise DuplicateAnalystResultError(f"duplicate result for {result.analyst_type}")
            if result.analyst_type not in self._expected_analysts:
                raise UnexpectedAnalystResultError(
                    f"result for {result.analyst_type} is not in expected_analysts"
                )
            by_type[result.analyst_type] = result

        analyst_results = tuple(by_type[t] for t in _CANONICAL_ORDER if t in by_type)

        anchor = analyst_results[0]
        provenance: dict[str, str] = {}
        for result in analyst_results:
            if (
                result.symbol != anchor.symbol
                or result.contract_type != anchor.contract_type
                or result.observation_time != anchor.observation_time
                or result.windows != anchor.windows
            ):
                raise InconsistentSnapshotError(
                    f"result for {result.analyst_type} does not share symbol/contract_type/"
                    "observation_time/windows with the other supplied results"
                )
            for key, value in result.provenance.items():
                if key in provenance and provenance[key] != value:
                    raise InconsistentSnapshotError(
                        f"provenance key {key!r} has conflicting values across supplied results"
                    )
                provenance[key] = value

        analyzed = tuple(
            t for t in self._expected_analysts if t in by_type and by_type[t].status is AnalystOutcome.ANALYZED
        )
        abstained = tuple(
            t for t in self._expected_analysts if t in by_type and by_type[t].status is AnalystOutcome.ABSTAINED
        )
        missing = tuple(t for t in self._expected_analysts if t not in by_type)

        expected_count = len(self._expected_analysts)
        analyzed_count = len(analyzed)
        abstained_count = len(abstained)
        missing_count = len(missing)
        usable_analyst_ratio = analyzed_count / expected_count

        if analyzed_count == 0:
            outcome = FlowSupervisorOutcome.INSUFFICIENT_EVIDENCE
        elif analyzed_count == expected_count:
            outcome = FlowSupervisorOutcome.ANALYZED
        else:
            outcome = FlowSupervisorOutcome.PARTIAL

        overall_quality = (
            worse_of_many(by_type[t].quality for t in analyzed) if analyzed else FeatureQuality.UNAVAILABLE
        )

        relationship_coherence, relationship_evidence_refs = _relationship_coherence(analyst_results)

        return FlowSupervisorResult(
            symbol=anchor.symbol,
            contract_type=anchor.contract_type,
            observation_time=anchor.observation_time,
            windows=anchor.windows,
            outcome=outcome,
            expected_analysts=self._expected_analysts,
            analyzed_analysts=analyzed,
            abstained_analysts=abstained,
            missing_analysts=missing,
            overall_quality=overall_quality,
            expected_count=expected_count,
            analyzed_count=analyzed_count,
            abstained_count=abstained_count,
            missing_count=missing_count,
            usable_analyst_ratio=usable_analyst_ratio,
            relationship_coherence=relationship_coherence,
            relationship_evidence_refs=relationship_evidence_refs,
            analyst_results=analyst_results,
            provenance=provenance,
        )


__all__ = ["DEFAULT_EXPECTED_ANALYSTS", "FlowSupervisor"]
