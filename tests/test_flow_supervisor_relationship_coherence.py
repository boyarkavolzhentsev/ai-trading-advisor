"""Stage 2C two-tier relationship-coherence algorithm tests.

Only ``PriceFlowRelationshipAnalyst`` observations under
PRICE_TAKER_RELATIONSHIP / PRICE_OPEN_INTEREST_RELATIONSHIP /
PRICE_LIQUIDATION_RELATIONSHIP participate - these are the only dimensions
that share one literal vocabulary (``PriceFlowRelationship``) across
independent flow domains. ``CorrelationRelationship`` observations never
participate (distinct vocabulary/semantics, approved decision).
"""

from __future__ import annotations

from datetime import timedelta

from app.core.enums.flow_analysis import AgreementVerdict, AnalysisDimension, AnalystType, CorrelationRelationship, PriceFlowRelationship
from app.core.models.analytics_window import AnalyticsWindow
from app.core.models.flow_analysis_result import FlowAnalysisResult
from app.core.models.flow_supervisor_result import FlowSupervisorResult
from app.flow_supervisor.supervisor import FlowSupervisor
from tests.flow_supervisor_support import abstained_result, analyzed_result, relationship_result

AGREEMENT = PriceFlowRelationship.AGREEMENT
DIVERGENCE = PriceFlowRelationship.DIVERGENCE


def _aggregate_with_relationship(relationship: FlowAnalysisResult) -> FlowSupervisorResult:
    results = (analyzed_result(AnalystType.TAKER_FLOW), relationship)
    return FlowSupervisor().aggregate(results)


def test_all_three_dimensions_all_agree_and_equal_yields_all_agree() -> None:
    relationship = relationship_result(
        taker_values=(AGREEMENT, AGREEMENT),
        oi_values=(AGREEMENT, AGREEMENT),
        liquidation_values=(AGREEMENT, AGREEMENT),
    )
    result = _aggregate_with_relationship(relationship)

    assert result.relationship_coherence is AgreementVerdict.ALL_AGREE
    assert len(result.relationship_evidence_refs) == 6  # 2 windows x 3 dimensions


def test_representatives_differ_yields_mixed() -> None:
    relationship = relationship_result(
        taker_values=(AGREEMENT, AGREEMENT),
        oi_values=(DIVERGENCE, DIVERGENCE),
        liquidation_values=(AGREEMENT, AGREEMENT),
    )
    result = _aggregate_with_relationship(relationship)

    assert result.relationship_coherence is AgreementVerdict.MIXED
    assert len(result.relationship_evidence_refs) == 6


def test_fewer_than_two_representatives_yields_insufficient_data() -> None:
    # only taker qualifies (2 windows, ALL_AGREE); oi/liquidation have zero observations
    relationship = relationship_result(taker_values=(AGREEMENT, AGREEMENT))
    result = _aggregate_with_relationship(relationship)

    assert result.relationship_coherence is AgreementVerdict.INSUFFICIENT_DATA
    assert result.relationship_evidence_refs == ()


def test_internally_mixed_dimension_excluded_from_tier_two() -> None:
    # oi is internally MIXED (AGREEMENT vs DIVERGENCE across its own 2 windows) -> excluded.
    # taker and liquidation both ALL_AGREE on AGREEMENT -> tier 2 sees 2 representatives, both equal.
    relationship = relationship_result(
        taker_values=(AGREEMENT, AGREEMENT),
        oi_values=(AGREEMENT, DIVERGENCE),
        liquidation_values=(AGREEMENT, AGREEMENT),
    )
    result = _aggregate_with_relationship(relationship)

    assert result.relationship_coherence is AgreementVerdict.ALL_AGREE
    # only taker's and liquidation's 2 windows each contribute - oi contributes nothing
    assert len(result.relationship_evidence_refs) == 4


def test_dimension_with_single_observation_is_insufficient_and_excluded() -> None:
    # liquidation has only 1 window -> agreement_of requires >=2 -> INSUFFICIENT_DATA -> excluded.
    # taker and oi both ALL_AGREE but differ -> tier 2 MIXED between exactly those two.
    relationship = relationship_result(
        taker_values=(AGREEMENT, AGREEMENT),
        oi_values=(DIVERGENCE, DIVERGENCE),
        liquidation_values=(AGREEMENT,),
    )
    result = _aggregate_with_relationship(relationship)

    assert result.relationship_coherence is AgreementVerdict.MIXED
    assert len(result.relationship_evidence_refs) == 4  # taker's 2 + oi's 2, not liquidation's 1


def test_more_windows_does_not_grant_extra_weight() -> None:
    # Scenario A: 2-vs-2 windows, opposing values -> MIXED.
    scenario_a = relationship_result(
        taker_values=(AGREEMENT, AGREEMENT),
        oi_values=(DIVERGENCE, DIVERGENCE),
    )
    result_a = _aggregate_with_relationship(scenario_a)

    # Scenario B: 5-vs-2 windows, same opposing values - a flat vote count would tip
    # 5:2 towards AGREEMENT; the two-tier algorithm must still report MIXED because
    # each dimension casts exactly one vote regardless of window count.
    heavy_windows = tuple(AnalyticsWindow(label=f"w{i}", duration=timedelta(seconds=i + 1)) for i in range(5))
    scenario_b = relationship_result(
        windows=heavy_windows,
        taker_values=(AGREEMENT,) * 5,
        oi_values=(DIVERGENCE, DIVERGENCE),
    )
    results_b = (
        analyzed_result(AnalystType.TAKER_FLOW, windows=heavy_windows),
        scenario_b,
    )
    result_b = FlowSupervisor().aggregate(results_b)

    assert result_a.relationship_coherence is AgreementVerdict.MIXED
    assert result_b.relationship_coherence is AgreementVerdict.MIXED


def test_correlation_observations_do_not_participate() -> None:
    without_correlation = relationship_result(
        taker_values=(AGREEMENT, AGREEMENT),
        oi_values=(AGREEMENT, AGREEMENT),
    )
    with_correlation = relationship_result(
        taker_values=(AGREEMENT, AGREEMENT),
        oi_values=(AGREEMENT, AGREEMENT),
        correlation_values=(CorrelationRelationship.NEGATIVE_RELATIONSHIP, CorrelationRelationship.NEGATIVE_RELATIONSHIP),
    )

    result_without = _aggregate_with_relationship(without_correlation)
    result_with = _aggregate_with_relationship(with_correlation)

    assert result_without.relationship_coherence == result_with.relationship_coherence == AgreementVerdict.ALL_AGREE
    # the extra correlation observations must never be cited as relationship evidence
    for analyst_idx, obs_idx in result_with.relationship_evidence_refs:
        obs = result_with.analyst_results[analyst_idx].observations[obs_idx]
        assert obs.dimension is not AnalysisDimension.CORRELATION_RELATIONSHIP


def test_relationship_analyst_missing_yields_insufficient_data() -> None:
    results = (analyzed_result(AnalystType.TAKER_FLOW),)  # PRICE_FLOW_RELATIONSHIP entirely absent
    result = FlowSupervisor().aggregate(results)

    assert result.relationship_coherence is AgreementVerdict.INSUFFICIENT_DATA
    assert result.relationship_evidence_refs == ()


def test_relationship_analyst_abstained_yields_insufficient_data() -> None:
    results = (
        analyzed_result(AnalystType.TAKER_FLOW),
        abstained_result(AnalystType.PRICE_FLOW_RELATIONSHIP),
    )
    result = FlowSupervisor().aggregate(results)

    assert result.relationship_coherence is AgreementVerdict.INSUFFICIENT_DATA
    assert result.relationship_evidence_refs == ()
