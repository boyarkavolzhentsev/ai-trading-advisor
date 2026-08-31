"""Stage 9: SessionGate is a pure, deterministic function of its two
explicit inputs - repeated calls on identical input produce byte-equivalent
results."""

from __future__ import annotations

from app.statistics.session import SessionGate
from tests.session_support import route_to_portfolio_and_session


def test_repeated_calls_produce_identical_result() -> None:
    portfolio_result, first = route_to_portfolio_and_session()
    second = SessionGate().evaluate(strategy_portfolio_result=portfolio_result, locked_override=False)
    third = SessionGate().evaluate(strategy_portfolio_result=portfolio_result, locked_override=False)
    assert first == second == third


def test_new_gate_instances_are_equivalent() -> None:
    portfolio_result, _ = route_to_portfolio_and_session()
    result_a = SessionGate().evaluate(strategy_portfolio_result=portfolio_result)
    result_b = SessionGate().evaluate(strategy_portfolio_result=portfolio_result)
    assert result_a == result_b
