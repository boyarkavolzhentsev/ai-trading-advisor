"""Stage 2C participation, outcome and coverage-formula tests."""

from __future__ import annotations

from app.core.enums.flow_analysis import AnalystType
from app.core.enums.flow_supervisor import FlowSupervisorOutcome
from app.flow_supervisor.supervisor import DEFAULT_EXPECTED_ANALYSTS, FlowSupervisor
from tests.flow_supervisor_support import abstained_result, analyzed_result, full_analyzed_set


def test_all_expected_analysts_analyzed() -> None:
    results = full_analyzed_set()
    result = FlowSupervisor().aggregate(results)

    assert result.outcome is FlowSupervisorOutcome.ANALYZED
    assert set(result.analyzed_analysts) == set(DEFAULT_EXPECTED_ANALYSTS)
    assert result.abstained_analysts == ()
    assert result.missing_analysts == ()
    assert result.analyzed_count == 6
    assert result.abstained_count == 0
    assert result.missing_count == 0
    assert result.expected_count == 6
    assert result.usable_analyst_ratio == 1.0


def test_some_analysts_abstained() -> None:
    results = list(full_analyzed_set())
    # replace FUNDING's analyzed result with an abstention
    results = [r for r in results if r.analyst_type is not AnalystType.FUNDING]
    results.append(abstained_result(AnalystType.FUNDING))

    result = FlowSupervisor().aggregate(results)

    assert result.outcome is FlowSupervisorOutcome.PARTIAL
    assert AnalystType.FUNDING in result.abstained_analysts
    assert AnalystType.FUNDING not in result.analyzed_analysts
    assert result.analyzed_count == 5
    assert result.abstained_count == 1
    assert result.missing_count == 0
    assert result.usable_analyst_ratio == 5 / 6


def test_all_supplied_analysts_abstained() -> None:
    results = tuple(abstained_result(analyst_type) for analyst_type in DEFAULT_EXPECTED_ANALYSTS)

    result = FlowSupervisor().aggregate(results)

    assert result.outcome is FlowSupervisorOutcome.INSUFFICIENT_EVIDENCE
    assert result.analyzed_count == 0
    assert result.abstained_count == 6
    assert result.missing_count == 0
    assert result.usable_analyst_ratio == 0.0


def test_one_expected_analyst_missing() -> None:
    results = [r for r in full_analyzed_set() if r.analyst_type is not AnalystType.LIQUIDATION]

    result = FlowSupervisor().aggregate(results)

    assert result.outcome is FlowSupervisorOutcome.PARTIAL
    assert result.missing_analysts == (AnalystType.LIQUIDATION,)
    assert result.missing_count == 1
    assert result.analyzed_count == 5
    assert result.usable_analyst_ratio == 5 / 6


def test_multiple_expected_analysts_missing() -> None:
    results = [
        r
        for r in full_analyzed_set()
        if r.analyst_type not in (AnalystType.LIQUIDATION, AnalystType.FUNDING, AnalystType.OPEN_INTEREST)
    ]

    result = FlowSupervisor().aggregate(results)

    assert result.outcome is FlowSupervisorOutcome.PARTIAL
    assert set(result.missing_analysts) == {AnalystType.LIQUIDATION, AnalystType.FUNDING, AnalystType.OPEN_INTEREST}
    assert result.missing_count == 3
    assert result.analyzed_count == 3
    assert result.usable_analyst_ratio == 3 / 6


def test_missing_and_abstained_are_distinguishable() -> None:
    results = [r for r in full_analyzed_set() if r.analyst_type not in (AnalystType.LIQUIDATION, AnalystType.FUNDING)]
    results.append(abstained_result(AnalystType.FUNDING))

    result = FlowSupervisor().aggregate(results)

    assert result.missing_analysts == (AnalystType.LIQUIDATION,)
    assert result.abstained_analysts == (AnalystType.FUNDING,)
    assert result.missing_count == 1
    assert result.abstained_count == 1


def test_outcome_insufficient_evidence_when_zero_analyzed_but_missing_present() -> None:
    results = (abstained_result(AnalystType.TAKER_FLOW),)  # rest missing

    result = FlowSupervisor().aggregate(results)

    assert result.outcome is FlowSupervisorOutcome.INSUFFICIENT_EVIDENCE
    assert result.analyzed_count == 0
    assert result.missing_count == 5


def test_custom_expected_analysts_ratio() -> None:
    supervisor = FlowSupervisor(expected_analysts=(AnalystType.TAKER_FLOW, AnalystType.FUNDING))
    results = (analyzed_result(AnalystType.TAKER_FLOW),)

    result = supervisor.aggregate(results)

    assert result.expected_count == 2
    assert result.analyzed_count == 1
    assert result.missing_count == 1
    assert result.usable_analyst_ratio == 0.5
    assert result.outcome is FlowSupervisorOutcome.PARTIAL
