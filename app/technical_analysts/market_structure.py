"""Deterministic Market Structure Analyst (Stage 3B).

Interprets Stage 3A ``MarketStructureFeatures`` only - never recomputes
swing detection or structural-break scanning (both remain Stage 3A
arithmetic). Relays Stage 3A's own neutral ``BreakDirection`` vocabulary
directly; never infers BOS/CHoCH, reversal, or continuation. A qualifying
snapshot with zero confirmed breaks is a legitimate ``NO_BREAK_CONFIRMED``
fact, never conflated with an unavailable/insufficient-history verdict.
"""

from __future__ import annotations

from app.core.enums.technical_analysis import (
    BreakSequencePattern,
    StructuralBreakPresence,
    TechnicalAnalysisDimension,
    TechnicalAnalystOutcome,
    TechnicalAnalystType,
)
from app.core.models.technical_analysis_result import TechnicalAnalysisObservation, TechnicalAnalysisResult
from app.core.models.technical_evidence import TechnicalEvidence
from app.core.models.technical_feature_snapshot import TechnicalFeatureSnapshot
from app.technical_analysts.base import abstain, make_evidence, qualifies

ABSTENTION_REASON = "no usable market structure evidence available"


class MarketStructureAnalyst:
    """Deterministic interpretation of Stage 3A confirmed swings/breaks."""

    analyst_type = TechnicalAnalystType.MARKET_STRUCTURE

    def analyze(self, snapshot: TechnicalFeatureSnapshot) -> TechnicalAnalysisResult:
        market_structure = snapshot.market_structure
        if not qualifies(market_structure.status):
            return abstain(TechnicalAnalystType.MARKET_STRUCTURE, snapshot, ABSTENTION_REASON)

        quality = market_structure.status.quality
        breaks = market_structure.breaks
        evidence: list[TechnicalEvidence] = []
        observations: list[TechnicalAnalysisObservation] = []

        presence_idx = len(evidence)
        evidence.append(
            make_evidence(
                feature_name="market_structure.breaks_count",
                observed_value=len(breaks),
                reference_value=0,
                quality=quality,
                source_timestamp=snapshot.observation_time,
                provenance=market_structure.source,
            )
        )
        presence = StructuralBreakPresence.BREAK_CONFIRMED if breaks else StructuralBreakPresence.NO_BREAK_CONFIRMED
        observations.append(
            TechnicalAnalysisObservation(
                dimension=TechnicalAnalysisDimension.STRUCTURAL_BREAK_PRESENCE,
                value=presence.value,
                quality=quality,
                evidence_refs=(presence_idx,),
            )
        )

        latest_idx = None
        if breaks:
            latest = breaks[-1]
            latest_idx = len(evidence)
            evidence.append(
                make_evidence(
                    feature_name="market_structure.latest_break.direction",
                    observed_value=latest.direction.value,
                    reference_value=None,
                    quality=quality,
                    source_timestamp=snapshot.observation_time,
                    provenance=market_structure.source,
                )
            )
            observations.append(
                TechnicalAnalysisObservation(
                    dimension=TechnicalAnalysisDimension.LATEST_BREAK_DIRECTION,
                    value=latest.direction.value,
                    quality=quality,
                    evidence_refs=(latest_idx,),
                )
            )

        if len(breaks) >= 2:
            latest = breaks[-1]
            second_latest = breaks[-2]
            second_idx = len(evidence)
            evidence.append(
                make_evidence(
                    feature_name="market_structure.second_latest_break.direction",
                    observed_value=second_latest.direction.value,
                    reference_value=None,
                    quality=quality,
                    source_timestamp=snapshot.observation_time,
                    provenance=market_structure.source,
                )
            )
            pattern = (
                BreakSequencePattern.REPEATED_DIRECTION
                if latest.direction == second_latest.direction
                else BreakSequencePattern.ALTERNATING
            )
            sequence_refs = (latest_idx, second_idx)
        else:
            pattern = BreakSequencePattern.INSUFFICIENT_DATA
            sequence_refs = (presence_idx,)
        observations.append(
            TechnicalAnalysisObservation(
                dimension=TechnicalAnalysisDimension.BREAK_SEQUENCE_PATTERN,
                value=pattern.value,
                quality=quality,
                evidence_refs=sequence_refs,
            )
        )

        return TechnicalAnalysisResult(
            analyst_type=TechnicalAnalystType.MARKET_STRUCTURE,
            symbol=snapshot.symbol,
            contract_type=snapshot.contract_type,
            timeframe=snapshot.timeframe,
            observation_time=snapshot.observation_time,
            last_closed_candle_time=snapshot.last_closed_candle_time,
            status=TechnicalAnalystOutcome.ANALYZED,
            observations=tuple(observations),
            evidence=tuple(evidence),
            quality=quality,
            provenance={"market_structure": market_structure.source},
        )


__all__ = ["MarketStructureAnalyst"]
