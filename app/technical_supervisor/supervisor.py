"""Deterministic Technical Supervisor (Stage 3C).

Aggregates already-produced Stage 3B ``TechnicalAnalysisResult`` objects
spanning an ``expected_analysts x expected_timeframes`` matrix for one
evaluation. Never invokes an analyst, never touches a
``TechnicalFeatureSnapshot``, never performs I/O - a pure, synchronous,
stateless function of its input sequence (see
``app.technical_supervisor.protocols.TechnicalSupervisorProtocol``).

Reuses ``app.technical.quality.worse_of_many`` - the technical contour's own
audited quality-fold primitive - rather than Flow's equivalent, keeping this
module Flow-independent. Reuses ``app.technical.timeframes.
DEFAULT_TECHNICAL_TIMEFRAMES`` as the default expected-timeframe preset
rather than redefining it.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.core.enums.market import Timeframe
from app.core.enums.quality import FeatureQuality
from app.core.enums.technical_analysis import (
    TechnicalAgreementVerdict,
    TechnicalAnalysisDimension,
    TechnicalAnalystOutcome,
    TechnicalAnalystType,
)
from app.core.enums.technical_supervisor import TechnicalSupervisorOutcome
from app.core.models.technical_analysis_result import TechnicalAnalysisResult
from app.core.models.technical_supervisor_result import (
    TechnicalAnalystSummary,
    TechnicalCoherenceResult,
    TechnicalSupervisorResult,
    TechnicalTimeframeSummary,
)
from app.technical.quality import worse_of_many
from app.technical.timeframes import DEFAULT_TECHNICAL_TIMEFRAMES
from app.technical_supervisor.errors import (
    DuplicateAnalystTimeframeResultError,
    EmptyResultsError,
    InconsistentSnapshotError,
    TechnicalSupervisorInputError,
    UnexpectedAnalystResultError,
    UnexpectedTimeframeResultError,
)

Cell = tuple[TechnicalAnalystType, Timeframe]

DEFAULT_EXPECTED_ANALYSTS: tuple[TechnicalAnalystType, ...] = tuple(TechnicalAnalystType)
"""Explicit, deterministic default expected-analyst set: all seven Stage 3B specialists."""

DEFAULT_EXPECTED_TIMEFRAMES: tuple[Timeframe, ...] = DEFAULT_TECHNICAL_TIMEFRAMES
"""Reuses Stage 3A's own approved default technical-contour timeframe preset."""

_ANALYST_CANONICAL_ORDER: tuple[TechnicalAnalystType, ...] = tuple(TechnicalAnalystType)
"""Fixed sort key for analyst tuples this module emits (enum declaration order)."""

_TIMEFRAME_CANONICAL_ORDER: tuple[Timeframe, ...] = tuple(Timeframe)
"""Fixed sort key for timeframe tuples this module emits (enum declaration order)."""

_FIXED_COHERENCE_DIMENSIONS: tuple[TechnicalAnalysisDimension, ...] = (
    TechnicalAnalysisDimension.RETURN_DIRECTION,
    TechnicalAnalysisDimension.SLOPE_DIRECTION,
    TechnicalAnalysisDimension.STRUCTURAL_SEQUENCE_BALANCE,
    TechnicalAnalysisDimension.LATEST_BREAK_DIRECTION,
    TechnicalAnalysisDimension.RANGE_EXPANSION_REFERENCE,
    TechnicalAnalysisDimension.ROC_SIGN,
    TechnicalAnalysisDimension.RSI_MIDPOINT_RELATION,
    TechnicalAnalysisDimension.NORMALIZED_RANGE_REFERENCE,
)
"""The only subject=None dimensions genuinely comparable across timeframes -
see the approved Stage 3C design report for why every other dimension is
either period-scoped (moving average, handled dynamically below), a
second-order verdict, or local single-candle geometry. Listed in
``TechnicalAnalysisDimension`` enum declaration order."""

_MA_DYNAMIC_DIMENSIONS: tuple[TechnicalAnalysisDimension, ...] = (
    TechnicalAnalysisDimension.PRICE_VS_SMA_POSITION,
    TechnicalAnalysisDimension.MA_SLOPE_DIRECTION,
    TechnicalAnalysisDimension.MULTI_PERIOD_MA_ORDERING,
)
"""Moving-average dimensions coherence-checked per distinct ``subject``
(period or period-pair identity) discovered from supplied
``MOVING_AVERAGE`` results - never a fixed, pre-declared period set."""


def _analyst_key(analyst_type: TechnicalAnalystType) -> int:
    return _ANALYST_CANONICAL_ORDER.index(analyst_type)


def _timeframe_key(timeframe: Timeframe) -> int:
    return _TIMEFRAME_CANONICAL_ORDER.index(timeframe)


def _tally_group(
    dimension: TechnicalAnalysisDimension,
    subject: str | None,
    entries: list[tuple[Timeframe, int, int, str]],
) -> TechnicalCoherenceResult:
    """Tally one coherence group's qualifying ``(timeframe, result_index,
    observation_index, value)`` entries into a verdict.

    ``entries`` must already be in canonical timeframe order (guaranteed by
    iterating the canonically ordered ``analyst_results`` tuple) and must
    carry at most one entry per timeframe (guaranteed: one analyst emits a
    given dimension/subject at most once per its own result).
    """
    if len(entries) < 2:
        return TechnicalCoherenceResult(
            dimension=dimension, subject=subject, verdict=TechnicalAgreementVerdict.INSUFFICIENT_DATA
        )

    values = {entry[3] for entry in entries}
    verdict = TechnicalAgreementVerdict.ALL_AGREE if len(values) == 1 else TechnicalAgreementVerdict.MIXED
    return TechnicalCoherenceResult(
        dimension=dimension,
        subject=subject,
        verdict=verdict,
        contributing_timeframes=tuple(entry[0] for entry in entries),
        evidence_refs=tuple((entry[1], entry[2]) for entry in entries),
    )


class TechnicalSupervisor:
    """Deterministic Stage 3C aggregator over Stage 3B analyst results."""

    def __init__(
        self,
        expected_analysts: tuple[TechnicalAnalystType, ...] = DEFAULT_EXPECTED_ANALYSTS,
        expected_timeframes: tuple[Timeframe, ...] = DEFAULT_EXPECTED_TIMEFRAMES,
    ) -> None:
        if not expected_analysts:
            raise TechnicalSupervisorInputError("expected_analysts must not be empty")
        if len(set(expected_analysts)) != len(expected_analysts):
            raise TechnicalSupervisorInputError("expected_analysts must not contain duplicate TechnicalAnalystType entries")
        if not expected_timeframes:
            raise TechnicalSupervisorInputError("expected_timeframes must not be empty")
        if len(set(expected_timeframes)) != len(expected_timeframes):
            raise TechnicalSupervisorInputError("expected_timeframes must not contain duplicate Timeframe entries")

        self._expected_analysts = tuple(sorted(expected_analysts, key=_analyst_key))
        self._expected_timeframes = tuple(sorted(expected_timeframes, key=_timeframe_key))

    @property
    def expected_analysts(self) -> tuple[TechnicalAnalystType, ...]:
        return self._expected_analysts

    @property
    def expected_timeframes(self) -> tuple[Timeframe, ...]:
        return self._expected_timeframes

    def aggregate(self, results: Sequence[TechnicalAnalysisResult]) -> TechnicalSupervisorResult:
        if not results:
            raise EmptyResultsError("aggregate requires at least one TechnicalAnalysisResult")

        by_key: dict[Cell, TechnicalAnalysisResult] = {}
        for result in results:
            key: Cell = (result.analyst_type, result.timeframe)
            if key in by_key:
                raise DuplicateAnalystTimeframeResultError(f"duplicate result for {key}")
            if result.analyst_type not in self._expected_analysts:
                raise UnexpectedAnalystResultError(
                    f"result analyst_type {result.analyst_type} is not in expected_analysts"
                )
            if result.timeframe not in self._expected_timeframes:
                raise UnexpectedTimeframeResultError(
                    f"result timeframe {result.timeframe} is not in expected_timeframes"
                )
            by_key[key] = result

        anchor = results[0]
        provenance: dict[str, str] = {}
        for result in results:
            if (
                result.symbol != anchor.symbol
                or result.contract_type != anchor.contract_type
                or result.observation_time != anchor.observation_time
            ):
                raise InconsistentSnapshotError(
                    f"result for {(result.analyst_type, result.timeframe)} does not share symbol/contract_type/"
                    "observation_time with the other supplied results"
                )
            for pkey, pvalue in result.provenance.items():
                if pkey in provenance and provenance[pkey] != pvalue:
                    raise InconsistentSnapshotError(f"provenance key {pkey!r} has conflicting values across supplied results")
                provenance[pkey] = pvalue

        # Canonical embedded ordering: timeframe-major, then analyst-minor.
        analyst_results = tuple(
            by_key[(a, t)] for t in self._expected_timeframes for a in self._expected_analysts if (a, t) in by_key
        )

        analyzed_cells = tuple(
            (a, t)
            for t in self._expected_timeframes
            for a in self._expected_analysts
            if (a, t) in by_key and by_key[(a, t)].status is TechnicalAnalystOutcome.ANALYZED
        )
        abstained_cells = tuple(
            (a, t)
            for t in self._expected_timeframes
            for a in self._expected_analysts
            if (a, t) in by_key and by_key[(a, t)].status is TechnicalAnalystOutcome.ABSTAINED
        )
        missing_cells = tuple(
            (a, t) for t in self._expected_timeframes for a in self._expected_analysts if (a, t) not in by_key
        )

        expected_count = len(self._expected_analysts) * len(self._expected_timeframes)
        analyzed_count = len(analyzed_cells)
        abstained_count = len(abstained_cells)
        missing_count = len(missing_cells)
        usable_cell_ratio = analyzed_count / expected_count

        if analyzed_count == 0:
            outcome = TechnicalSupervisorOutcome.INSUFFICIENT_EVIDENCE
        elif analyzed_count == expected_count:
            outcome = TechnicalSupervisorOutcome.ANALYZED
        else:
            outcome = TechnicalSupervisorOutcome.PARTIAL

        overall_quality = (
            worse_of_many(by_key[cell].quality for cell in analyzed_cells) if analyzed_cells else FeatureQuality.UNAVAILABLE
        )

        per_timeframe_summaries = self._build_timeframe_summaries(analyzed_cells, abstained_cells, missing_cells, by_key)
        per_analyst_summaries = self._build_analyst_summaries(analyzed_cells, abstained_cells, missing_cells, by_key)
        coherence = self._build_coherence(analyst_results)

        return TechnicalSupervisorResult(
            symbol=anchor.symbol,
            contract_type=anchor.contract_type,
            observation_time=anchor.observation_time,
            outcome=outcome,
            expected_analysts=self._expected_analysts,
            expected_timeframes=self._expected_timeframes,
            analyzed_cells=analyzed_cells,
            abstained_cells=abstained_cells,
            missing_cells=missing_cells,
            expected_count=expected_count,
            analyzed_count=analyzed_count,
            abstained_count=abstained_count,
            missing_count=missing_count,
            usable_cell_ratio=usable_cell_ratio,
            overall_quality=overall_quality,
            per_timeframe_summaries=per_timeframe_summaries,
            per_analyst_summaries=per_analyst_summaries,
            coherence=coherence,
            analyst_results=analyst_results,
            provenance=provenance,
        )

    def _build_timeframe_summaries(
        self,
        analyzed_cells: tuple[Cell, ...],
        abstained_cells: tuple[Cell, ...],
        missing_cells: tuple[Cell, ...],
        by_key: dict[Cell, TechnicalAnalysisResult],
    ) -> tuple[TechnicalTimeframeSummary, ...]:
        analyzed_set, abstained_set, missing_set = set(analyzed_cells), set(abstained_cells), set(missing_cells)
        summaries = []
        for t in self._expected_timeframes:
            analyzed = tuple(a for a in self._expected_analysts if (a, t) in analyzed_set)
            abstained = tuple(a for a in self._expected_analysts if (a, t) in abstained_set)
            missing = tuple(a for a in self._expected_analysts if (a, t) in missing_set)
            quality = worse_of_many(by_key[(a, t)].quality for a in analyzed) if analyzed else FeatureQuality.UNAVAILABLE
            total = len(analyzed) + len(abstained) + len(missing)
            summaries.append(
                TechnicalTimeframeSummary(
                    timeframe=t,
                    analyzed_analysts=analyzed,
                    abstained_analysts=abstained,
                    missing_analysts=missing,
                    analyzed_count=len(analyzed),
                    abstained_count=len(abstained),
                    missing_count=len(missing),
                    usable_ratio=len(analyzed) / total,
                    quality=quality,
                )
            )
        return tuple(summaries)

    def _build_analyst_summaries(
        self,
        analyzed_cells: tuple[Cell, ...],
        abstained_cells: tuple[Cell, ...],
        missing_cells: tuple[Cell, ...],
        by_key: dict[Cell, TechnicalAnalysisResult],
    ) -> tuple[TechnicalAnalystSummary, ...]:
        analyzed_set, abstained_set, missing_set = set(analyzed_cells), set(abstained_cells), set(missing_cells)
        summaries = []
        for a in self._expected_analysts:
            analyzed = tuple(t for t in self._expected_timeframes if (a, t) in analyzed_set)
            abstained = tuple(t for t in self._expected_timeframes if (a, t) in abstained_set)
            missing = tuple(t for t in self._expected_timeframes if (a, t) in missing_set)
            quality = worse_of_many(by_key[(a, t)].quality for t in analyzed) if analyzed else FeatureQuality.UNAVAILABLE
            total = len(analyzed) + len(abstained) + len(missing)
            summaries.append(
                TechnicalAnalystSummary(
                    analyst_type=a,
                    analyzed_timeframes=analyzed,
                    abstained_timeframes=abstained,
                    missing_timeframes=missing,
                    analyzed_count=len(analyzed),
                    abstained_count=len(abstained),
                    missing_count=len(missing),
                    usable_ratio=len(analyzed) / total,
                    quality=quality,
                )
            )
        return tuple(summaries)

    def _build_coherence(self, analyst_results: tuple[TechnicalAnalysisResult, ...]) -> tuple[TechnicalCoherenceResult, ...]:
        coherence: list[TechnicalCoherenceResult] = []

        for dimension in _FIXED_COHERENCE_DIMENSIONS:
            entries = [
                (result.timeframe, idx, obs_idx, observation.value)
                for idx, result in enumerate(analyst_results)
                if result.status is TechnicalAnalystOutcome.ANALYZED
                for obs_idx, observation in enumerate(result.observations)
                if observation.dimension is dimension
            ]
            coherence.append(_tally_group(dimension, None, entries))

        ma_groups: dict[tuple[TechnicalAnalysisDimension, str], list[tuple[Timeframe, int, int, str]]] = {}
        for idx, result in enumerate(analyst_results):
            if result.analyst_type is not TechnicalAnalystType.MOVING_AVERAGE:
                continue
            if result.status is not TechnicalAnalystOutcome.ANALYZED:
                continue
            for obs_idx, observation in enumerate(result.observations):
                if observation.dimension in _MA_DYNAMIC_DIMENSIONS and observation.subject is not None:
                    ma_groups.setdefault((observation.dimension, observation.subject), []).append(
                        (result.timeframe, idx, obs_idx, observation.value)
                    )

        for dimension, subject in sorted(ma_groups, key=lambda key: (_MA_DYNAMIC_DIMENSIONS.index(key[0]), key[1])):
            coherence.append(_tally_group(dimension, subject, ma_groups[(dimension, subject)]))

        return tuple(coherence)


__all__ = ["DEFAULT_EXPECTED_ANALYSTS", "DEFAULT_EXPECTED_TIMEFRAMES", "TechnicalSupervisor"]
