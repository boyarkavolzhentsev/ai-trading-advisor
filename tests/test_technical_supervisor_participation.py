"""Stage 3C participation-matrix and outcome tests."""

from __future__ import annotations

from app.core.enums.market import Timeframe
from app.core.enums.technical_analysis import TechnicalAnalystType
from app.core.enums.technical_supervisor import TechnicalSupervisorOutcome
from app.technical_supervisor.supervisor import TechnicalSupervisor
from tests.technical_supervisor_support import abstained_result, analyzed_result, full_matrix


def test_all_cells_analyzed_yields_analyzed_outcome() -> None:
    result = TechnicalSupervisor().aggregate(full_matrix())

    assert result.outcome is TechnicalSupervisorOutcome.ANALYZED
    assert result.expected_count == 42
    assert result.analyzed_count == 42
    assert result.abstained_count == 0
    assert result.missing_count == 0
    assert result.usable_cell_ratio == 1.0
    assert result.missing_cells == ()
    assert result.abstained_cells == ()


def test_one_abstained_cell_yields_partial() -> None:
    results = [
        r for r in full_matrix() if not (r.analyst_type is TechnicalAnalystType.TREND and r.timeframe is Timeframe.M1)
    ]
    results.append(abstained_result(TechnicalAnalystType.TREND, Timeframe.M1))

    result = TechnicalSupervisor().aggregate(results)

    assert result.outcome is TechnicalSupervisorOutcome.PARTIAL
    assert result.abstained_cells == ((TechnicalAnalystType.TREND, Timeframe.M1),)
    assert result.abstained_count == 1
    assert result.analyzed_count == 41
    assert result.missing_count == 0


def test_one_missing_cell_yields_partial() -> None:
    results = [
        r for r in full_matrix() if not (r.analyst_type is TechnicalAnalystType.MOMENTUM and r.timeframe is Timeframe.H4)
    ]

    result = TechnicalSupervisor().aggregate(results)

    assert result.outcome is TechnicalSupervisorOutcome.PARTIAL
    assert result.missing_cells == ((TechnicalAnalystType.MOMENTUM, Timeframe.H4),)
    assert result.missing_count == 1
    assert result.analyzed_count == 41


def test_multiple_missing_cells() -> None:
    excluded = {
        (TechnicalAnalystType.MOMENTUM, Timeframe.H4),
        (TechnicalAnalystType.VOLATILITY, Timeframe.D1),
        (TechnicalAnalystType.TREND, Timeframe.M1),
    }
    results = [r for r in full_matrix() if (r.analyst_type, r.timeframe) not in excluded]

    result = TechnicalSupervisor().aggregate(results)

    assert result.missing_count == 3
    assert set(result.missing_cells) == excluded
    assert result.analyzed_count == 39


def test_missing_and_abstained_are_distinguishable() -> None:
    results = [
        r
        for r in full_matrix()
        if not (r.analyst_type is TechnicalAnalystType.TREND and r.timeframe is Timeframe.M1)
        and not (r.analyst_type is TechnicalAnalystType.MOMENTUM and r.timeframe is Timeframe.H4)
    ]
    results.append(abstained_result(TechnicalAnalystType.MOMENTUM, Timeframe.H4))
    # TREND/M1 is left entirely absent -> MISSING

    result = TechnicalSupervisor().aggregate(results)

    assert (TechnicalAnalystType.MOMENTUM, Timeframe.H4) in result.abstained_cells
    assert (TechnicalAnalystType.TREND, Timeframe.M1) in result.missing_cells
    assert (TechnicalAnalystType.MOMENTUM, Timeframe.H4) not in result.missing_cells
    assert (TechnicalAnalystType.TREND, Timeframe.M1) not in result.abstained_cells


def test_outcome_insufficient_evidence_when_zero_analyzed() -> None:
    supervisor = TechnicalSupervisor(expected_analysts=(TechnicalAnalystType.TREND,), expected_timeframes=(Timeframe.M1,))
    results = (abstained_result(TechnicalAnalystType.TREND, Timeframe.M1),)

    result = supervisor.aggregate(results)

    assert result.outcome is TechnicalSupervisorOutcome.INSUFFICIENT_EVIDENCE
    assert result.analyzed_count == 0


def test_outcome_insufficient_evidence_with_missing_and_abstained_mixed() -> None:
    supervisor = TechnicalSupervisor(
        expected_analysts=(TechnicalAnalystType.TREND, TechnicalAnalystType.MOMENTUM),
        expected_timeframes=(Timeframe.M1,),
    )
    results = (abstained_result(TechnicalAnalystType.TREND, Timeframe.M1),)  # MOMENTUM/M1 missing entirely

    result = supervisor.aggregate(results)

    assert result.outcome is TechnicalSupervisorOutcome.INSUFFICIENT_EVIDENCE
    assert result.analyzed_count == 0
    assert result.abstained_count == 1
    assert result.missing_count == 1


def test_custom_small_matrix_ratio() -> None:
    supervisor = TechnicalSupervisor(
        expected_analysts=(TechnicalAnalystType.TREND, TechnicalAnalystType.MOMENTUM, TechnicalAnalystType.VOLATILITY),
        expected_timeframes=(Timeframe.M1, Timeframe.H4),
    )
    results = (
        analyzed_result(TechnicalAnalystType.TREND, Timeframe.M1),
        analyzed_result(TechnicalAnalystType.MOMENTUM, Timeframe.M1),
    )

    result = supervisor.aggregate(results)

    assert result.expected_count == 6
    assert result.analyzed_count == 2
    assert result.usable_cell_ratio == 2 / 6


def test_buckets_exactly_partition_expected_matrix() -> None:
    result = TechnicalSupervisor().aggregate(full_matrix())
    expected = {(a, t) for a in result.expected_analysts for t in result.expected_timeframes}
    union = set(result.analyzed_cells) | set(result.abstained_cells) | set(result.missing_cells)
    assert union == expected
    assert len(union) == len(result.analyzed_cells) + len(result.abstained_cells) + len(result.missing_cells)
