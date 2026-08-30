"""Stage 8 ``PortfolioSupervisor`` is a pure, deterministic function of its
input: same ``StrategyRiskResult`` in twice must yield byte-identical
``StrategyPortfolioResult`` output, and the implementation must never touch
the wall clock, ``random``, or ``uuid``. All monetary arithmetic uses
``Decimal`` only."""

from __future__ import annotations

import ast
import inspect
from decimal import Decimal
from pathlib import Path

from app.diversification.supervisor import PortfolioSupervisor
from tests.market_evaluation_support import full_technical_result
from tests.risk_gate_support import route_judge_gate_and_risk


def test_repeated_calls_are_identical() -> None:
    _, risk_result = route_judge_gate_and_risk(technical=full_technical_result())
    supervisor = PortfolioSupervisor()
    first = supervisor.evaluate(strategy_risk_result=risk_result)
    second = supervisor.evaluate(strategy_risk_result=risk_result)
    assert first == second


def test_repeated_calls_on_empty_risk_result_are_identical() -> None:
    _, risk_result = route_judge_gate_and_risk()
    supervisor = PortfolioSupervisor()
    assert supervisor.evaluate(strategy_risk_result=risk_result) == supervisor.evaluate(strategy_risk_result=risk_result)


def test_source_has_no_wall_clock_random_or_uuid_calls() -> None:
    path = Path(inspect.getfile(PortfolioSupervisor))
    tree = ast.parse(path.read_text(encoding="utf-8"))
    forbidden_attrs = {"now", "utcnow", "today"}
    forbidden_modules = {"random", "uuid", "secrets", "time"}

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = (alias.name for alias in node.names)
            module = getattr(node, "module", None)
            offending = forbidden_modules & set(names)
            if module in forbidden_modules:
                offending.add(module)
            assert not offending, f"supervisor.py imports forbidden module(s): {offending}"
        if isinstance(node, ast.Attribute) and node.attr in forbidden_attrs:
            raise AssertionError(f"supervisor.py calls a wall-clock method: .{node.attr}(...)")


def test_no_float_used_for_monetary_fields() -> None:
    _, risk_result = route_judge_gate_and_risk(technical=full_technical_result())
    result = PortfolioSupervisor().evaluate(strategy_risk_result=risk_result)
    for family_result in result.family_results:
        assert family_result.portfolio_allocated_risk is None or isinstance(family_result.portfolio_allocated_risk, Decimal)


def test_no_rounding_calls_in_supervisor() -> None:
    path = Path(inspect.getfile(PortfolioSupervisor))
    source = path.read_text(encoding="utf-8")
    for forbidden in ("round(", "quantize", "ROUND_"):
        assert forbidden not in source, f"supervisor.py contains a forbidden rounding construct: {forbidden!r}"
