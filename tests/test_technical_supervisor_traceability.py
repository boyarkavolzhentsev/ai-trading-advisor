"""Stage 3C end-to-end evidence traceability and serialization tests.

TechnicalSupervisorResult -> TechnicalCoherenceResult.evidence_refs ->
embedded TechnicalAnalysisResult -> TechnicalAnalysisObservation ->
evidence_refs -> TechnicalEvidence -> provenance/source_timestamp. Every hop
must resolve, including after a JSON round trip.
"""

from __future__ import annotations

from app.core.enums.market import Timeframe
from app.core.enums.technical_analysis import TechnicalAnalysisDimension, TechnicalAnalystType
from app.core.models.technical_supervisor_result import TechnicalSupervisorResult
from app.technical_supervisor.supervisor import TechnicalSupervisor
from tests.technical_supervisor_support import dimension_result, moving_average_result


def _all_agree_result() -> TechnicalSupervisorResult:
    results = [
        dimension_result(TechnicalAnalystType.TREND, Timeframe.M1, TechnicalAnalysisDimension.RETURN_DIRECTION, "UPWARD"),
        dimension_result(TechnicalAnalystType.TREND, Timeframe.H4, TechnicalAnalysisDimension.RETURN_DIRECTION, "UPWARD"),
        moving_average_result(Timeframe.M1, price_vs_sma={"20": "ABOVE_SMA"}),
        moving_average_result(Timeframe.H4, price_vs_sma={"20": "ABOVE_SMA"}),
    ]
    supervisor = TechnicalSupervisor(
        expected_analysts=(TechnicalAnalystType.TREND, TechnicalAnalystType.MOVING_AVERAGE),
        expected_timeframes=(Timeframe.M1, Timeframe.H4),
    )
    return supervisor.aggregate(results)


def test_every_coherence_evidence_ref_resolves() -> None:
    result = _all_agree_result()
    assert result.coherence

    resolved_any = False
    for coherence in result.coherence:
        for result_idx, observation_idx in coherence.evidence_refs:
            resolved_any = True
            analyst_result = result.analyst_results[result_idx]
            observation = analyst_result.observations[observation_idx]

            assert observation.dimension is coherence.dimension
            assert observation.subject == coherence.subject

            for evidence_idx in observation.evidence_refs:
                evidence = analyst_result.evidence[evidence_idx]
                assert evidence.provenance
                assert evidence.source_timestamp == analyst_result.observation_time

    assert resolved_any


def test_provenance_survives_end_to_end() -> None:
    results = (
        dimension_result(
            TechnicalAnalystType.TREND,
            Timeframe.M1,
            TechnicalAnalysisDimension.RETURN_DIRECTION,
            "UPWARD",
            provenance={"trend": "technical_engine"},
        ),
        dimension_result(
            TechnicalAnalystType.TREND,
            Timeframe.H4,
            TechnicalAnalysisDimension.RETURN_DIRECTION,
            "UPWARD",
            provenance={"trend": "technical_engine"},
        ),
    )
    supervisor = TechnicalSupervisor(expected_analysts=(TechnicalAnalystType.TREND,), expected_timeframes=(Timeframe.M1, Timeframe.H4))

    result = supervisor.aggregate(results)

    assert result.provenance == {"trend": "technical_engine"}
    for analyst_result in result.analyst_results:
        assert analyst_result.provenance  # each embedded result keeps its own provenance too


def test_embedded_results_are_unchanged_from_input() -> None:
    original_m1 = dimension_result(TechnicalAnalystType.TREND, Timeframe.M1, TechnicalAnalysisDimension.RETURN_DIRECTION, "UPWARD")
    original_h4 = dimension_result(TechnicalAnalystType.TREND, Timeframe.H4, TechnicalAnalysisDimension.RETURN_DIRECTION, "UPWARD")
    supervisor = TechnicalSupervisor(expected_analysts=(TechnicalAnalystType.TREND,), expected_timeframes=(Timeframe.M1, Timeframe.H4))

    result = supervisor.aggregate((original_m1, original_h4))

    embedded_by_timeframe = {r.timeframe: r for r in result.analyst_results}
    assert embedded_by_timeframe[Timeframe.M1] == original_m1
    assert embedded_by_timeframe[Timeframe.H4] == original_h4


def test_serialization_round_trip_preserves_traceability() -> None:
    result = _all_agree_result()

    payload = result.model_dump_json()
    restored = TechnicalSupervisorResult.model_validate_json(payload)

    assert restored == result
    for coherence in restored.coherence:
        for result_idx, observation_idx in coherence.evidence_refs:
            analyst_result = restored.analyst_results[result_idx]
            observation = analyst_result.observations[observation_idx]
            for evidence_idx in observation.evidence_refs:
                assert analyst_result.evidence[evidence_idx] is not None
