"""Stage 2C quality/coverage independence tests.

``overall_quality`` and ``usable_analyst_ratio`` must vary independently:
full coverage with degraded quality must look different from low coverage
with pristine quality, and neither field may be derived from the other.
"""

from __future__ import annotations

from app.core.enums.flow_analysis import AnalystType
from app.core.enums.quality import FeatureQuality
from app.flow_supervisor.supervisor import DEFAULT_EXPECTED_ANALYSTS, FlowSupervisor
from tests.flow_supervisor_support import abstained_result, analyzed_result


def test_full_coverage_with_degraded_quality() -> None:
    results = tuple(
        analyzed_result(analyst_type, quality=FeatureQuality.STALE) for analyst_type in DEFAULT_EXPECTED_ANALYSTS
    )

    result = FlowSupervisor().aggregate(results)

    assert result.usable_analyst_ratio == 1.0
    assert result.overall_quality is FeatureQuality.STALE


def test_low_coverage_with_valid_quality() -> None:
    results = (analyzed_result(AnalystType.TAKER_FLOW, quality=FeatureQuality.VALID),)

    result = FlowSupervisor().aggregate(results)

    assert result.usable_analyst_ratio == 1 / 6
    assert result.overall_quality is FeatureQuality.VALID


def test_zero_analyzed_yields_unavailable_quality() -> None:
    results = tuple(abstained_result(analyst_type) for analyst_type in DEFAULT_EXPECTED_ANALYSTS)

    result = FlowSupervisor().aggregate(results)

    assert result.overall_quality is FeatureQuality.UNAVAILABLE


def test_worst_of_analyzed_qualities_wins() -> None:
    results = (
        analyzed_result(AnalystType.TAKER_FLOW, quality=FeatureQuality.VALID),
        analyzed_result(AnalystType.LIQUIDATION, quality=FeatureQuality.PARTIAL),
        analyzed_result(AnalystType.FUNDING, quality=FeatureQuality.STALE),
    )

    result = FlowSupervisor().aggregate(results)

    assert result.overall_quality is FeatureQuality.STALE


def test_abstained_and_missing_do_not_affect_overall_quality() -> None:
    results = (
        analyzed_result(AnalystType.TAKER_FLOW, quality=FeatureQuality.VALID),
        abstained_result(AnalystType.LIQUIDATION),
        # FUNDING, OPEN_INTEREST, ORDER_BOOK_LIQUIDITY, PRICE_FLOW_RELATIONSHIP missing
    )

    result = FlowSupervisor().aggregate(results)

    assert result.overall_quality is FeatureQuality.VALID
    assert result.missing_count == 4


def test_embedded_analyst_result_qualities_are_preserved_unchanged() -> None:
    original = analyzed_result(AnalystType.TAKER_FLOW, quality=FeatureQuality.PARTIAL)
    result = FlowSupervisor().aggregate((original,))

    embedded = next(r for r in result.analyst_results if r.analyst_type is AnalystType.TAKER_FLOW)
    assert embedded == original
    assert embedded.quality is FeatureQuality.PARTIAL
