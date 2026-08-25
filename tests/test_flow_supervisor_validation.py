"""Stage 2C fail-fast input-validation tests.

Every case here is a programming/orchestration error, never a legitimate
market condition - Stage 2C must raise, not degrade into a structured
result (see ``app.flow_supervisor.errors``).
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.core.enums.flow_analysis import AnalystType
from app.core.enums.instrument import ContractType
from app.core.models.analytics_window import AnalyticsWindow
from app.flow_supervisor.errors import (
    DuplicateAnalystResultError,
    EmptyResultsError,
    FlowSupervisorInputError,
    InconsistentSnapshotError,
    UnexpectedAnalystResultError,
)
from app.flow_supervisor.supervisor import FlowSupervisor
from tests.flow_supervisor_support import NOW, WINDOWS, analyzed_result


def test_empty_results_raises() -> None:
    with pytest.raises(EmptyResultsError):
        FlowSupervisor().aggregate(())


def test_duplicate_analyst_type_raises() -> None:
    results = (
        analyzed_result(AnalystType.TAKER_FLOW),
        analyzed_result(AnalystType.TAKER_FLOW),
    )
    with pytest.raises(DuplicateAnalystResultError):
        FlowSupervisor().aggregate(results)


def test_unexpected_analyst_type_raises() -> None:
    supervisor = FlowSupervisor(expected_analysts=(AnalystType.TAKER_FLOW,))
    results = (analyzed_result(AnalystType.LIQUIDATION),)
    with pytest.raises(UnexpectedAnalystResultError):
        supervisor.aggregate(results)


def test_mismatched_symbol_raises() -> None:
    results = (
        analyzed_result(AnalystType.TAKER_FLOW, symbol="BTCUSDT"),
        analyzed_result(AnalystType.LIQUIDATION, symbol="ETHUSDT"),
    )
    with pytest.raises(InconsistentSnapshotError):
        FlowSupervisor().aggregate(results)


def test_mismatched_contract_type_raises() -> None:
    results = (
        analyzed_result(AnalystType.TAKER_FLOW, contract_type=ContractType.PERPETUAL),
        analyzed_result(AnalystType.LIQUIDATION, contract_type=ContractType.SPOT),
    )
    with pytest.raises(InconsistentSnapshotError):
        FlowSupervisor().aggregate(results)


def test_mismatched_observation_time_raises() -> None:
    results = (
        analyzed_result(AnalystType.TAKER_FLOW, observation_time=NOW),
        analyzed_result(AnalystType.LIQUIDATION, observation_time=NOW + timedelta(seconds=1)),
    )
    with pytest.raises(InconsistentSnapshotError):
        FlowSupervisor().aggregate(results)


def test_mismatched_windows_raises() -> None:
    other_windows = (AnalyticsWindow(label="5m", duration=timedelta(minutes=5)),)
    results = (
        analyzed_result(AnalystType.TAKER_FLOW, windows=WINDOWS),
        analyzed_result(AnalystType.LIQUIDATION, windows=other_windows),
    )
    with pytest.raises(InconsistentSnapshotError):
        FlowSupervisor().aggregate(results)


def test_provenance_collision_raises() -> None:
    results = (
        analyzed_result(AnalystType.TAKER_FLOW, provenance={"taker_flow": "stream-a"}),
        analyzed_result(AnalystType.LIQUIDATION, provenance={"taker_flow": "stream-b"}),
    )
    with pytest.raises(InconsistentSnapshotError):
        FlowSupervisor().aggregate(results)


def test_provenance_agreement_does_not_raise() -> None:
    results = (
        analyzed_result(AnalystType.TAKER_FLOW, provenance={"taker_flow": "stream-a"}),
        analyzed_result(AnalystType.LIQUIDATION, provenance={"taker_flow": "stream-a"}),
    )
    result = FlowSupervisor().aggregate(results)
    assert result.provenance["taker_flow"] == "stream-a"


def test_constructor_rejects_empty_expected_analysts() -> None:
    with pytest.raises(FlowSupervisorInputError):
        FlowSupervisor(expected_analysts=())


def test_constructor_rejects_duplicate_expected_analysts() -> None:
    with pytest.raises(FlowSupervisorInputError):
        FlowSupervisor(expected_analysts=(AnalystType.TAKER_FLOW, AnalystType.TAKER_FLOW))
