"""Stage 3C multi-timeframe coherence tests.

Covers every approved fixed-dimension coherence group (ALL_AGREE/MIXED/
INSUFFICIENT_DATA), explicit FLAT/ZERO/AT_MIDPOINT/MIXED_STRUCTURE/
AT_REFERENCE/no-break semantics, and the dynamic moving-average period/pair
coherence groups.
"""

from __future__ import annotations

import pytest

from app.core.enums.market import Timeframe
from app.core.enums.technical_analysis import TechnicalAgreementVerdict, TechnicalAnalysisDimension, TechnicalAnalystType
from app.technical_supervisor.supervisor import TechnicalSupervisor
from tests.technical_supervisor_support import dimension_result, moving_average_result

_FIXED_DIMENSION_CASES = [
    (TechnicalAnalystType.TREND, TechnicalAnalysisDimension.RETURN_DIRECTION, "UPWARD", "DOWNWARD"),
    (TechnicalAnalystType.TREND, TechnicalAnalysisDimension.SLOPE_DIRECTION, "UPWARD", "FLAT"),
    (TechnicalAnalystType.TREND, TechnicalAnalysisDimension.STRUCTURAL_SEQUENCE_BALANCE, "UPWARD_STRUCTURE", "MIXED_STRUCTURE"),
    (TechnicalAnalystType.MOMENTUM, TechnicalAnalysisDimension.ROC_SIGN, "POSITIVE", "ZERO"),
    (TechnicalAnalystType.MOMENTUM, TechnicalAnalysisDimension.RSI_MIDPOINT_RELATION, "ABOVE_MIDPOINT", "AT_MIDPOINT"),
    (TechnicalAnalystType.MARKET_STRUCTURE, TechnicalAnalysisDimension.LATEST_BREAK_DIRECTION, "UPWARD_BREAK", "DOWNWARD_BREAK"),
    (TechnicalAnalystType.VOLATILITY, TechnicalAnalysisDimension.RANGE_EXPANSION_REFERENCE, "ABOVE_REFERENCE", "AT_REFERENCE"),
    (TechnicalAnalystType.RANGE_STATE, TechnicalAnalysisDimension.NORMALIZED_RANGE_REFERENCE, "BELOW_REFERENCE", "AT_REFERENCE"),
]


def _aggregate_with_dimension_at_timeframes(analyst_type, dimension, values_by_timeframe):
    supervisor = TechnicalSupervisor(expected_analysts=(analyst_type,), expected_timeframes=tuple(values_by_timeframe))
    results = [dimension_result(analyst_type, tf, dimension, value) for tf, value in values_by_timeframe.items()]
    result = supervisor.aggregate(results)
    matches = [c for c in result.coherence if c.dimension is dimension and c.subject is None]
    assert len(matches) == 1
    return matches[0]


@pytest.mark.parametrize("analyst_type,dimension,value_a,value_b", _FIXED_DIMENSION_CASES)
def test_fixed_dimension_all_agree(analyst_type, dimension, value_a, value_b) -> None:
    coherence = _aggregate_with_dimension_at_timeframes(
        analyst_type, dimension, {Timeframe.M1: value_a, Timeframe.H4: value_a}
    )
    assert coherence.verdict is TechnicalAgreementVerdict.ALL_AGREE
    assert set(coherence.contributing_timeframes) == {Timeframe.M1, Timeframe.H4}
    assert len(coherence.evidence_refs) == 2


@pytest.mark.parametrize("analyst_type,dimension,value_a,value_b", _FIXED_DIMENSION_CASES)
def test_fixed_dimension_mixed(analyst_type, dimension, value_a, value_b) -> None:
    coherence = _aggregate_with_dimension_at_timeframes(
        analyst_type, dimension, {Timeframe.M1: value_a, Timeframe.H4: value_b}
    )
    assert coherence.verdict is TechnicalAgreementVerdict.MIXED
    assert len(coherence.evidence_refs) == 2  # neutral/boundary categories are never filtered out


@pytest.mark.parametrize("analyst_type,dimension,value_a,value_b", _FIXED_DIMENSION_CASES)
def test_fixed_dimension_insufficient_data_with_single_timeframe(analyst_type, dimension, value_a, value_b) -> None:
    coherence = _aggregate_with_dimension_at_timeframes(analyst_type, dimension, {Timeframe.M1: value_a})
    assert coherence.verdict is TechnicalAgreementVerdict.INSUFFICIENT_DATA
    assert coherence.contributing_timeframes == ()
    assert coherence.evidence_refs == ()


def test_flat_return_direction_is_valid_and_creates_mixed() -> None:
    coherence = _aggregate_with_dimension_at_timeframes(
        TechnicalAnalystType.TREND,
        TechnicalAnalysisDimension.RETURN_DIRECTION,
        {Timeframe.M1: "UPWARD", Timeframe.M5: "UPWARD", Timeframe.M15: "FLAT"},
    )
    assert coherence.verdict is TechnicalAgreementVerdict.MIXED
    assert len(coherence.evidence_refs) == 3  # FLAT is not filtered out


def test_zero_roc_sign_is_valid_category() -> None:
    coherence = _aggregate_with_dimension_at_timeframes(
        TechnicalAnalystType.MOMENTUM,
        TechnicalAnalysisDimension.ROC_SIGN,
        {Timeframe.M1: "ZERO", Timeframe.H4: "ZERO"},
    )
    assert coherence.verdict is TechnicalAgreementVerdict.ALL_AGREE


def test_at_midpoint_rsi_is_valid_category_not_excluded() -> None:
    coherence = _aggregate_with_dimension_at_timeframes(
        TechnicalAnalystType.MOMENTUM,
        TechnicalAnalysisDimension.RSI_MIDPOINT_RELATION,
        {Timeframe.M1: "AT_MIDPOINT", Timeframe.H4: "ABOVE_MIDPOINT"},
    )
    assert coherence.verdict is TechnicalAgreementVerdict.MIXED
    assert len(coherence.evidence_refs) == 2


def test_mixed_structure_is_valid_information_not_missing() -> None:
    coherence = _aggregate_with_dimension_at_timeframes(
        TechnicalAnalystType.TREND,
        TechnicalAnalysisDimension.STRUCTURAL_SEQUENCE_BALANCE,
        {Timeframe.M1: "MIXED_STRUCTURE", Timeframe.H4: "MIXED_STRUCTURE"},
    )
    assert coherence.verdict is TechnicalAgreementVerdict.ALL_AGREE


def test_at_reference_is_valid_category_for_range_dimensions() -> None:
    coherence = _aggregate_with_dimension_at_timeframes(
        TechnicalAnalystType.VOLATILITY,
        TechnicalAnalysisDimension.RANGE_EXPANSION_REFERENCE,
        {Timeframe.M1: "AT_REFERENCE", Timeframe.H4: "AT_REFERENCE"},
    )
    assert coherence.verdict is TechnicalAgreementVerdict.ALL_AGREE


def test_no_break_does_not_participate_in_latest_break_direction_coherence() -> None:
    results = [
        dimension_result(
            TechnicalAnalystType.MARKET_STRUCTURE, Timeframe.M1, TechnicalAnalysisDimension.STRUCTURAL_BREAK_PRESENCE, "NO_BREAK_CONFIRMED"
        ),
        dimension_result(
            TechnicalAnalystType.MARKET_STRUCTURE, Timeframe.H4, TechnicalAnalysisDimension.LATEST_BREAK_DIRECTION, "UPWARD_BREAK"
        ),
    ]
    supervisor = TechnicalSupervisor(
        expected_analysts=(TechnicalAnalystType.MARKET_STRUCTURE,), expected_timeframes=(Timeframe.M1, Timeframe.H4)
    )

    result = supervisor.aggregate(results)
    coherence = next(c for c in result.coherence if c.dimension is TechnicalAnalysisDimension.LATEST_BREAK_DIRECTION)

    assert coherence.verdict is TechnicalAgreementVerdict.INSUFFICIENT_DATA
    assert coherence.contributing_timeframes == ()


def test_ma_same_period_across_timeframes_all_agree() -> None:
    results = [
        moving_average_result(Timeframe.M1, price_vs_sma={"20": "ABOVE_SMA"}),
        moving_average_result(Timeframe.H4, price_vs_sma={"20": "ABOVE_SMA"}),
    ]
    supervisor = TechnicalSupervisor(
        expected_analysts=(TechnicalAnalystType.MOVING_AVERAGE,), expected_timeframes=(Timeframe.M1, Timeframe.H4)
    )

    result = supervisor.aggregate(results)
    coherence = next(
        c for c in result.coherence if c.dimension is TechnicalAnalysisDimension.PRICE_VS_SMA_POSITION and c.subject == "20"
    )

    assert coherence.verdict is TechnicalAgreementVerdict.ALL_AGREE


def test_ma_same_period_mixed() -> None:
    results = [
        moving_average_result(Timeframe.M1, price_vs_sma={"20": "ABOVE_SMA"}),
        moving_average_result(Timeframe.H4, price_vs_sma={"20": "BELOW_SMA"}),
    ]
    supervisor = TechnicalSupervisor(
        expected_analysts=(TechnicalAnalystType.MOVING_AVERAGE,), expected_timeframes=(Timeframe.M1, Timeframe.H4)
    )

    result = supervisor.aggregate(results)
    coherence = next(
        c for c in result.coherence if c.dimension is TechnicalAnalysisDimension.PRICE_VS_SMA_POSITION and c.subject == "20"
    )

    assert coherence.verdict is TechnicalAgreementVerdict.MIXED


def test_ma_different_periods_not_conflated() -> None:
    results = [
        moving_average_result(Timeframe.M1, price_vs_sma={"20": "ABOVE_SMA"}),
        moving_average_result(Timeframe.H4, price_vs_sma={"50": "BELOW_SMA"}),
    ]
    supervisor = TechnicalSupervisor(
        expected_analysts=(TechnicalAnalystType.MOVING_AVERAGE,), expected_timeframes=(Timeframe.M1, Timeframe.H4)
    )

    result = supervisor.aggregate(results)
    groups = {
        (c.dimension, c.subject): c for c in result.coherence if c.dimension is TechnicalAnalysisDimension.PRICE_VS_SMA_POSITION
    }

    assert len(groups) == 2  # never merged into one group
    assert groups[(TechnicalAnalysisDimension.PRICE_VS_SMA_POSITION, "20")].verdict is TechnicalAgreementVerdict.INSUFFICIENT_DATA
    assert groups[(TechnicalAnalysisDimension.PRICE_VS_SMA_POSITION, "50")].verdict is TechnicalAgreementVerdict.INSUFFICIENT_DATA


def test_ma_single_qualifying_timeframe_is_insufficient_data() -> None:
    results = [moving_average_result(Timeframe.M1, price_vs_sma={"20": "ABOVE_SMA"})]
    supervisor = TechnicalSupervisor(expected_analysts=(TechnicalAnalystType.MOVING_AVERAGE,), expected_timeframes=(Timeframe.M1,))

    result = supervisor.aggregate(results)
    coherence = next(c for c in result.coherence if c.dimension is TechnicalAnalysisDimension.PRICE_VS_SMA_POSITION)

    assert coherence.verdict is TechnicalAgreementVerdict.INSUFFICIENT_DATA


def test_ma_period_pair_identity_preserved() -> None:
    results = [
        moving_average_result(Timeframe.M1, ordering=("20_vs_50", "FASTER_ABOVE_SLOWER")),
        moving_average_result(Timeframe.H4, ordering=("20_vs_50", "FASTER_ABOVE_SLOWER")),
    ]
    supervisor = TechnicalSupervisor(
        expected_analysts=(TechnicalAnalystType.MOVING_AVERAGE,), expected_timeframes=(Timeframe.M1, Timeframe.H4)
    )

    result = supervisor.aggregate(results)
    coherence = next(c for c in result.coherence if c.dimension is TechnicalAnalysisDimension.MULTI_PERIOD_MA_ORDERING)

    assert coherence.subject == "20_vs_50"
    assert coherence.verdict is TechnicalAgreementVerdict.ALL_AGREE


def test_ma_period_pairs_not_conflated_with_different_pairs() -> None:
    results = [
        moving_average_result(Timeframe.M1, ordering=("20_vs_50", "FASTER_ABOVE_SLOWER")),
        moving_average_result(Timeframe.H4, ordering=("10_vs_100", "FASTER_ABOVE_SLOWER")),
    ]
    supervisor = TechnicalSupervisor(
        expected_analysts=(TechnicalAnalystType.MOVING_AVERAGE,), expected_timeframes=(Timeframe.M1, Timeframe.H4)
    )

    result = supervisor.aggregate(results)
    groups = {
        c.subject: c for c in result.coherence if c.dimension is TechnicalAnalysisDimension.MULTI_PERIOD_MA_ORDERING
    }

    assert set(groups) == {"20_vs_50", "10_vs_100"}
    assert all(c.verdict is TechnicalAgreementVerdict.INSUFFICIENT_DATA for c in groups.values())


def test_ma_dynamic_subject_discovery_is_deterministic_regardless_of_input_order() -> None:
    a = moving_average_result(Timeframe.M1, price_vs_sma={"20": "ABOVE_SMA", "50": "BELOW_SMA"})
    b = moving_average_result(Timeframe.H4, price_vs_sma={"20": "ABOVE_SMA", "50": "BELOW_SMA"})
    supervisor = TechnicalSupervisor(
        expected_analysts=(TechnicalAnalystType.MOVING_AVERAGE,), expected_timeframes=(Timeframe.M1, Timeframe.H4)
    )

    forward = supervisor.aggregate([a, b])
    reversed_order = supervisor.aggregate([b, a])

    assert forward.coherence == reversed_order.coherence
