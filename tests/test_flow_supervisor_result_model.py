"""Tests for app.core.models.flow_supervisor_result: FlowSupervisorResult validators."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.enums.flow_analysis import AgreementVerdict, AnalystType, PriceFlowRelationship
from app.core.enums.flow_supervisor import FlowSupervisorOutcome
from app.core.enums.quality import FeatureQuality
from app.core.models.flow_supervisor_result import FlowSupervisorResult
from tests.flow_supervisor_support import CONTRACT_TYPE, NOW, WINDOWS, abstained_result, analyzed_result, relationship_result


def _valid_result(**overrides: object) -> FlowSupervisorResult:
    taker = analyzed_result(AnalystType.TAKER_FLOW)
    fields: dict[str, object] = dict(
        symbol="BTCUSDT",
        contract_type=CONTRACT_TYPE,
        observation_time=NOW,
        windows=WINDOWS,
        outcome=FlowSupervisorOutcome.PARTIAL,
        expected_analysts=(AnalystType.TAKER_FLOW, AnalystType.FUNDING),
        analyzed_analysts=(AnalystType.TAKER_FLOW,),
        abstained_analysts=(),
        missing_analysts=(AnalystType.FUNDING,),
        overall_quality=FeatureQuality.VALID,
        expected_count=2,
        analyzed_count=1,
        abstained_count=0,
        missing_count=1,
        usable_analyst_ratio=0.5,
        relationship_coherence=AgreementVerdict.INSUFFICIENT_DATA,
        relationship_evidence_refs=(),
        analyst_results=(taker,),
        provenance={"taker_flow": "test"},
    )
    fields.update(overrides)
    return FlowSupervisorResult(**fields)


def _relationship_valid_result(**overrides: object) -> FlowSupervisorResult:
    """Baseline mirroring what ``FlowSupervisor.aggregate`` itself would build
    for two fully ANALYZED, ALL_AGREE analysts - used to isolate the
    relationship-coherence/evidence-ref validators from the participation
    validators exercised by ``_valid_result``.
    """
    taker = analyzed_result(AnalystType.TAKER_FLOW)
    rel = relationship_result(
        taker_values=(PriceFlowRelationship.AGREEMENT, PriceFlowRelationship.AGREEMENT),
        oi_values=(PriceFlowRelationship.AGREEMENT, PriceFlowRelationship.AGREEMENT),
    )
    fields: dict[str, object] = dict(
        symbol="BTCUSDT",
        contract_type=CONTRACT_TYPE,
        observation_time=NOW,
        windows=WINDOWS,
        outcome=FlowSupervisorOutcome.ANALYZED,
        expected_analysts=(AnalystType.TAKER_FLOW, AnalystType.PRICE_FLOW_RELATIONSHIP),
        analyzed_analysts=(AnalystType.TAKER_FLOW, AnalystType.PRICE_FLOW_RELATIONSHIP),
        abstained_analysts=(),
        missing_analysts=(),
        overall_quality=FeatureQuality.VALID,
        expected_count=2,
        analyzed_count=2,
        abstained_count=0,
        missing_count=0,
        usable_analyst_ratio=1.0,
        relationship_coherence=AgreementVerdict.ALL_AGREE,
        relationship_evidence_refs=((1, 0), (1, 1), (1, 2), (1, 3)),
        analyst_results=(taker, rel),
        provenance={"taker_flow": "test", "price_context": "test"},
    )
    fields.update(overrides)
    return FlowSupervisorResult(**fields)


def test_valid_result_roundtrips() -> None:
    result = _valid_result()
    restored = FlowSupervisorResult.model_validate(result.model_dump())
    assert restored == result


def test_relationship_valid_result_roundtrips() -> None:
    result = _relationship_valid_result()
    restored = FlowSupervisorResult.model_validate(result.model_dump())
    assert restored == result


def test_duplicate_expected_analysts_rejected() -> None:
    with pytest.raises(ValidationError):
        _valid_result(expected_analysts=(AnalystType.TAKER_FLOW, AnalystType.TAKER_FLOW))


def test_participation_must_partition_expected() -> None:
    with pytest.raises(ValidationError):
        _valid_result(missing_analysts=())  # FUNDING now belongs nowhere


def test_participation_buckets_must_be_disjoint() -> None:
    with pytest.raises(ValidationError):
        _valid_result(abstained_analysts=(AnalystType.TAKER_FLOW,))  # also in analyzed_analysts


def test_expected_count_must_match_expected_analysts_length() -> None:
    with pytest.raises(ValidationError):
        _valid_result(expected_count=3)


def test_usable_ratio_must_equal_analyzed_over_expected() -> None:
    with pytest.raises(ValidationError):
        _valid_result(usable_analyst_ratio=0.9)


def test_analyst_result_type_must_be_in_expected_analysts() -> None:
    stray = analyzed_result(AnalystType.LIQUIDATION)  # not in this baseline's expected_analysts
    with pytest.raises(ValidationError):
        _valid_result(analyst_results=(analyzed_result(AnalystType.TAKER_FLOW), stray))


def test_analyst_result_status_must_match_participation_bucket() -> None:
    mismatched = abstained_result(AnalystType.TAKER_FLOW)
    with pytest.raises(ValidationError):
        _valid_result(analyst_results=(mismatched,))  # bucketed as analyzed, but status is ABSTAINED


def test_analyst_result_snapshot_mismatch_rejected() -> None:
    mismatched = analyzed_result(AnalystType.TAKER_FLOW, symbol="ETHUSDT")
    with pytest.raises(ValidationError):
        _valid_result(analyst_results=(mismatched,))


def test_relationship_refs_out_of_bounds_analyst_index_rejected() -> None:
    with pytest.raises(ValidationError):
        _relationship_valid_result(relationship_evidence_refs=((5, 0),))


def test_relationship_refs_out_of_bounds_observation_index_rejected() -> None:
    with pytest.raises(ValidationError):
        _relationship_valid_result(relationship_evidence_refs=((1, 99),))


def test_insufficient_data_coherence_must_not_carry_refs() -> None:
    with pytest.raises(ValidationError):
        _relationship_valid_result(relationship_coherence=AgreementVerdict.INSUFFICIENT_DATA)


def test_all_agree_coherence_must_carry_refs() -> None:
    with pytest.raises(ValidationError):
        _relationship_valid_result(relationship_evidence_refs=())


def test_result_is_frozen() -> None:
    result = _valid_result()
    with pytest.raises(ValidationError):
        result.overall_quality = FeatureQuality.STALE  # type: ignore[misc]
