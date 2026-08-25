"""Stage 2C end-to-end evidence traceability and serialization tests.

FlowSupervisorResult -> relationship_evidence_refs -> embedded
FlowAnalysisResult -> FlowAnalysisObservation -> evidence_refs -> FlowEvidence
-> provenance/source_timestamp. Every hop must resolve, including after a
JSON round trip.
"""

from __future__ import annotations

from app.core.enums.flow_analysis import AgreementVerdict, AnalystType, PriceFlowRelationship
from app.core.models.flow_supervisor_result import FlowSupervisorResult
from app.flow_supervisor.supervisor import FlowSupervisor
from tests.flow_supervisor_support import analyzed_result, relationship_result

AGREEMENT = PriceFlowRelationship.AGREEMENT


def _all_agree_result() -> FlowSupervisorResult:
    relationship = relationship_result(
        taker_values=(AGREEMENT, AGREEMENT),
        oi_values=(AGREEMENT, AGREEMENT),
    )
    results = (analyzed_result(AnalystType.TAKER_FLOW), relationship)
    return FlowSupervisor().aggregate(results)


def test_every_relationship_evidence_ref_resolves() -> None:
    result = _all_agree_result()
    assert result.relationship_coherence is AgreementVerdict.ALL_AGREE
    assert result.relationship_evidence_refs

    for analyst_idx, observation_idx in result.relationship_evidence_refs:
        analyst_result = result.analyst_results[analyst_idx]
        assert analyst_result.analyst_type is AnalystType.PRICE_FLOW_RELATIONSHIP

        observation = analyst_result.observations[observation_idx]
        for evidence_idx in observation.evidence_refs:
            evidence = analyst_result.evidence[evidence_idx]
            assert evidence.provenance
            assert evidence.source_timestamp == analyst_result.observation_time


def test_provenance_preserved_end_to_end() -> None:
    results = (
        analyzed_result(AnalystType.TAKER_FLOW, provenance={"taker_flow": "test:taker"}),
        analyzed_result(AnalystType.LIQUIDATION, provenance={"liquidation": "test:liquidation"}),
    )
    result = FlowSupervisor().aggregate(results)

    assert result.provenance == {"taker_flow": "test:taker", "liquidation": "test:liquidation"}
    for analyst_result in result.analyst_results:
        assert analyst_result.provenance  # each embedded result keeps its own provenance too


def test_embedded_results_are_unchanged_from_input() -> None:
    original_taker = analyzed_result(AnalystType.TAKER_FLOW)
    original_relationship = relationship_result(taker_values=(AGREEMENT, AGREEMENT))
    result = FlowSupervisor().aggregate((original_taker, original_relationship))

    embedded_by_type = {r.analyst_type: r for r in result.analyst_results}
    assert embedded_by_type[AnalystType.TAKER_FLOW] == original_taker
    assert embedded_by_type[AnalystType.PRICE_FLOW_RELATIONSHIP] == original_relationship


def test_serialization_round_trip_preserves_traceability() -> None:
    result = _all_agree_result()

    payload = result.model_dump_json()
    restored = FlowSupervisorResult.model_validate_json(payload)

    assert restored == result
    for analyst_idx, observation_idx in restored.relationship_evidence_refs:
        analyst_result = restored.analyst_results[analyst_idx]
        observation = analyst_result.observations[observation_idx]
        for evidence_idx in observation.evidence_refs:
            assert analyst_result.evidence[evidence_idx] is not None
