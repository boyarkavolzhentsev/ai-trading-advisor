"""Stage 3C configuration and input-validation tests."""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.core.enums.instrument import ContractType
from app.core.enums.market import Timeframe
from app.core.enums.technical_analysis import TechnicalAnalystType
from app.technical.timeframes import DEFAULT_TECHNICAL_TIMEFRAMES
from app.technical_supervisor.errors import (
    DuplicateAnalystTimeframeResultError,
    EmptyResultsError,
    InconsistentSnapshotError,
    TechnicalSupervisorInputError,
    UnexpectedAnalystResultError,
    UnexpectedTimeframeResultError,
)
from app.technical_supervisor.supervisor import DEFAULT_EXPECTED_ANALYSTS, DEFAULT_EXPECTED_TIMEFRAMES, TechnicalSupervisor
from tests.technical_supervisor_support import NOW, analyzed_result


def test_default_expected_analysts_are_all_seven_types() -> None:
    supervisor = TechnicalSupervisor()
    assert supervisor.expected_analysts == tuple(TechnicalAnalystType)
    assert len(supervisor.expected_analysts) == 7
    assert DEFAULT_EXPECTED_ANALYSTS == tuple(TechnicalAnalystType)


def test_default_expected_timeframes_reuse_stage_3a_preset() -> None:
    supervisor = TechnicalSupervisor()
    assert supervisor.expected_timeframes == DEFAULT_TECHNICAL_TIMEFRAMES
    assert DEFAULT_EXPECTED_TIMEFRAMES == DEFAULT_TECHNICAL_TIMEFRAMES


def test_default_matrix_is_42_cells() -> None:
    supervisor = TechnicalSupervisor()
    assert len(supervisor.expected_analysts) * len(supervisor.expected_timeframes) == 42


def test_custom_expected_analysts() -> None:
    custom = (TechnicalAnalystType.MOMENTUM, TechnicalAnalystType.TREND)
    supervisor = TechnicalSupervisor(expected_analysts=custom)
    assert supervisor.expected_analysts == (TechnicalAnalystType.TREND, TechnicalAnalystType.MOMENTUM)


def test_custom_expected_timeframes() -> None:
    custom = (Timeframe.H4, Timeframe.M1)
    supervisor = TechnicalSupervisor(expected_timeframes=custom)
    assert supervisor.expected_timeframes == (Timeframe.M1, Timeframe.H4)


def test_constructor_rejects_empty_expected_analysts() -> None:
    with pytest.raises(TechnicalSupervisorInputError):
        TechnicalSupervisor(expected_analysts=())


def test_constructor_rejects_duplicate_expected_analysts() -> None:
    with pytest.raises(TechnicalSupervisorInputError):
        TechnicalSupervisor(expected_analysts=(TechnicalAnalystType.TREND, TechnicalAnalystType.TREND))


def test_constructor_rejects_empty_expected_timeframes() -> None:
    with pytest.raises(TechnicalSupervisorInputError):
        TechnicalSupervisor(expected_timeframes=())


def test_constructor_rejects_duplicate_expected_timeframes() -> None:
    with pytest.raises(TechnicalSupervisorInputError):
        TechnicalSupervisor(expected_timeframes=(Timeframe.M1, Timeframe.M1))


def test_empty_results_raises() -> None:
    with pytest.raises(EmptyResultsError):
        TechnicalSupervisor().aggregate(())


def test_duplicate_analyst_timeframe_raises() -> None:
    result = analyzed_result(TechnicalAnalystType.TREND, Timeframe.M1)
    with pytest.raises(DuplicateAnalystTimeframeResultError):
        TechnicalSupervisor().aggregate((result, result))


def test_unexpected_analyst_raises() -> None:
    supervisor = TechnicalSupervisor(expected_analysts=(TechnicalAnalystType.TREND,))
    stray = analyzed_result(TechnicalAnalystType.MOMENTUM, Timeframe.M1)
    with pytest.raises(UnexpectedAnalystResultError):
        supervisor.aggregate((stray,))


def test_unexpected_timeframe_raises() -> None:
    supervisor = TechnicalSupervisor(expected_timeframes=(Timeframe.M1,))
    stray = analyzed_result(TechnicalAnalystType.TREND, Timeframe.H4)
    with pytest.raises(UnexpectedTimeframeResultError):
        supervisor.aggregate((stray,))


def test_mismatched_symbol_raises() -> None:
    results = (
        analyzed_result(TechnicalAnalystType.TREND, Timeframe.M1, symbol="BTCUSDT"),
        analyzed_result(TechnicalAnalystType.MOMENTUM, Timeframe.M1, symbol="ETHUSDT"),
    )
    with pytest.raises(InconsistentSnapshotError):
        TechnicalSupervisor().aggregate(results)


def test_mismatched_contract_type_raises() -> None:
    results = (
        analyzed_result(TechnicalAnalystType.TREND, Timeframe.M1, contract_type=ContractType.PERPETUAL),
        analyzed_result(TechnicalAnalystType.MOMENTUM, Timeframe.M1, contract_type=ContractType.SPOT),
    )
    with pytest.raises(InconsistentSnapshotError):
        TechnicalSupervisor().aggregate(results)


def test_mismatched_observation_time_raises() -> None:
    results = (
        analyzed_result(TechnicalAnalystType.TREND, Timeframe.M1, observation_time=NOW),
        analyzed_result(TechnicalAnalystType.MOMENTUM, Timeframe.M1, observation_time=NOW + timedelta(minutes=1)),
    )
    with pytest.raises(InconsistentSnapshotError):
        TechnicalSupervisor().aggregate(results)


def test_different_last_closed_candle_time_across_timeframes_is_accepted() -> None:
    results = (
        analyzed_result(TechnicalAnalystType.TREND, Timeframe.M1, last_closed_candle_time=NOW - timedelta(minutes=1)),
        analyzed_result(TechnicalAnalystType.TREND, Timeframe.H4, last_closed_candle_time=NOW - timedelta(hours=4)),
    )
    supervisor = TechnicalSupervisor(expected_analysts=(TechnicalAnalystType.TREND,), expected_timeframes=(Timeframe.M1, Timeframe.H4))

    result = supervisor.aggregate(results)

    assert result.analyzed_count == 2


def test_provenance_collision_raises() -> None:
    results = (
        analyzed_result(TechnicalAnalystType.TREND, Timeframe.M1, provenance={"trend": "engine_a"}),
        analyzed_result(TechnicalAnalystType.TREND, Timeframe.H4, provenance={"trend": "engine_b"}),
    )
    with pytest.raises(InconsistentSnapshotError):
        TechnicalSupervisor().aggregate(results)


def test_provenance_agreement_does_not_raise() -> None:
    results = (
        analyzed_result(TechnicalAnalystType.TREND, Timeframe.M1, provenance={"trend": "technical_engine"}),
        analyzed_result(TechnicalAnalystType.TREND, Timeframe.H4, provenance={"trend": "technical_engine"}),
    )
    result = TechnicalSupervisor().aggregate(results)
    assert result.provenance == {"trend": "technical_engine"}
