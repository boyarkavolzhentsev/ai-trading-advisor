"""Shared deterministic primitives for Stage 3B technical analysts.

Every helper here only classifies or compares already-computed Stage 3A
values - mirrors ``app.flow_analysts.base``'s "judge, never repair" stance
one contour over. No helper recomputes an indicator, touches
``app.technical`` calculators, or picks a calibrated magnitude threshold;
every comparison here is against a mathematically neutral reference (zero,
an exact midpoint, a ratio of 1, or an exact natural boundary).

Every Stage 3B analyst reads exactly one Stage 3A feature block, which
already carries exactly one ``FeatureStatus`` - unlike Flow's per-window
quality merging, there is never more than one quality value to fold per
analyst, so no ``worse_of_many`` helper is needed here.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import TypeVar

from app.core.enums.technical_analysis import (
    BoundaryPosition,
    MidpointRelation,
    ReferenceComparison,
    TechnicalAgreementVerdict,
    TechnicalAnalystOutcome,
    TechnicalAnalystType,
)
from app.core.enums.quality import FeatureQuality
from app.core.models.base import Timestamp
from app.core.models.feature_status import FeatureStatus
from app.core.models.technical_analysis_result import TechnicalAnalysisResult
from app.core.models.technical_evidence import TechnicalEvidence
from app.core.models.technical_feature_snapshot import TechnicalFeatureSnapshot

Number = Decimal | float
E = TypeVar("E")


def qualifies(status: FeatureStatus) -> bool:
    """Whether a Stage 3A feature block's quality is usable at all.

    ``UNAVAILABLE`` is the only quality that disqualifies a block outright;
    ``PARTIAL``/``STALE`` blocks are real, previously-computed values and
    remain usable, carrying their reduced quality forward into whatever
    observation consumes them.
    """
    return status.quality is not FeatureQuality.UNAVAILABLE


def sign_category(value: Number | None, *, positive: E, negative: E, zero: E) -> E | None:
    """Classify a signed value into a caller-supplied 3-way category.

    Returns ``None`` (never a fabricated category) when ``value`` is
    ``None``. A genuine zero always maps to ``zero`` - it is never conflated
    with a missing value.
    """
    if value is None:
        return None
    if value > 0:
        return positive
    if value < 0:
        return negative
    return zero


def reference_comparison(value: Number | None, *, reference: Number = Decimal(1)) -> ReferenceComparison | None:
    """Compare an already-computed ratio against the neutral reference ``1.0``.

    ``None`` (never fabricated) when ``value`` is ``None``.
    """
    if value is None:
        return None
    if value > reference:
        return ReferenceComparison.ABOVE_REFERENCE
    if value < reference:
        return ReferenceComparison.BELOW_REFERENCE
    return ReferenceComparison.AT_REFERENCE


def midpoint_relation(value: Number | None, *, midpoint: Number) -> MidpointRelation | None:
    """Compare an already-computed value against its own natural midpoint.

    ``None`` (never fabricated) when ``value`` is ``None``.
    """
    if value is None:
        return None
    if value > midpoint:
        return MidpointRelation.ABOVE_MIDPOINT
    if value < midpoint:
        return MidpointRelation.BELOW_MIDPOINT
    return MidpointRelation.AT_MIDPOINT


def boundary_position(value: Number | None, *, minimum: Number, maximum: Number) -> BoundaryPosition | None:
    """Compare an already-computed, naturally-bounded value against its own
    exact minimum/maximum. ``None`` (never fabricated) when ``value`` is
    ``None``."""
    if value is None:
        return None
    if value == minimum:
        return BoundaryPosition.AT_MINIMUM
    if value == maximum:
        return BoundaryPosition.AT_MAXIMUM
    return BoundaryPosition.BETWEEN_BOUNDS


def agreement_of(values: Sequence[object]) -> TechnicalAgreementVerdict:
    """Tally already-qualifying categorical values into a shared verdict.

    Requires at least 2 entries to be meaningful; the caller must already
    have filtered out non-directional/unavailable entries - "no value" or
    "not directional" is never treated as (dis)agreement.
    """
    if len(values) < 2:
        return TechnicalAgreementVerdict.INSUFFICIENT_DATA
    return TechnicalAgreementVerdict.ALL_AGREE if len(set(values)) == 1 else TechnicalAgreementVerdict.MIXED


def make_evidence(
    *,
    feature_name: str,
    observed_value: object,
    reference_value: object | None,
    quality: FeatureQuality,
    source_timestamp: Timestamp,
    provenance: str,
) -> TechnicalEvidence:
    """Build one traceable ``TechnicalEvidence`` entry from an already-computed value."""
    return TechnicalEvidence(
        feature_name=feature_name,
        observed_value=str(observed_value),
        reference_value=str(reference_value) if reference_value is not None else None,
        quality=quality,
        source_timestamp=source_timestamp,
        provenance=provenance,
    )


def abstain(
    analyst_type: TechnicalAnalystType, snapshot: TechnicalFeatureSnapshot, reason: str
) -> TechnicalAnalysisResult:
    """Build the uniform ``ABSTAINED`` result shape shared by every analyst."""
    return TechnicalAnalysisResult(
        analyst_type=analyst_type,
        symbol=snapshot.symbol,
        contract_type=snapshot.contract_type,
        timeframe=snapshot.timeframe,
        observation_time=snapshot.observation_time,
        last_closed_candle_time=snapshot.last_closed_candle_time,
        status=TechnicalAnalystOutcome.ABSTAINED,
        quality=FeatureQuality.UNAVAILABLE,
        abstention_reasons=(reason,),
    )


__all__ = [
    "abstain",
    "agreement_of",
    "boundary_position",
    "make_evidence",
    "midpoint_relation",
    "qualifies",
    "reference_comparison",
    "sign_category",
]
