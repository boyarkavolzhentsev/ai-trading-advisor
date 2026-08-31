"""Stage 9 ``SessionGateProtocol``/``StatisticsAggregatorProtocol`` are
runtime-checkable and ``SessionGate``/``StatisticsAggregator`` satisfy them
structurally."""

from __future__ import annotations

import inspect

from app.statistics.aggregator import StatisticsAggregator
from app.statistics.protocols import SessionGateProtocol, StatisticsAggregatorProtocol
from app.statistics.session import SessionGate


def test_session_gate_satisfies_protocol() -> None:
    assert isinstance(SessionGate(), SessionGateProtocol)


def test_statistics_aggregator_satisfies_protocol() -> None:
    assert isinstance(StatisticsAggregator(), StatisticsAggregatorProtocol)


def test_session_gate_protocol_is_runtime_checkable() -> None:
    assert getattr(SessionGateProtocol, "_is_runtime_protocol", False) is True


def test_statistics_aggregator_protocol_is_runtime_checkable() -> None:
    assert getattr(StatisticsAggregatorProtocol, "_is_runtime_protocol", False) is True


def test_session_gate_evaluate_signature_has_no_extra_parameters() -> None:
    signature = inspect.signature(SessionGateProtocol.evaluate)
    params = list(signature.parameters)
    assert params == ["self", "strategy_portfolio_result", "locked_override"]
    assert signature.parameters["strategy_portfolio_result"].kind is inspect.Parameter.KEYWORD_ONLY
    assert signature.parameters["locked_override"].kind is inspect.Parameter.KEYWORD_ONLY
    assert signature.parameters["locked_override"].default is False


def test_statistics_aggregator_aggregate_signature_has_no_extra_parameters() -> None:
    signature = inspect.signature(StatisticsAggregatorProtocol.aggregate)
    params = list(signature.parameters)
    assert params == ["self", "records"]
    assert signature.parameters["records"].kind is inspect.Parameter.KEYWORD_ONLY
