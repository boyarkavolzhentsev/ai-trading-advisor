"""Stage 7 ``RiskGate`` is a pure, deterministic function of its input: same
inputs in twice must yield byte-identical ``StrategyRiskResult`` output, and
the implementation must never touch the wall clock, ``random``, or ``uuid``.
All monetary arithmetic uses ``Decimal`` only."""

from __future__ import annotations

import ast
import inspect
from decimal import Decimal
from pathlib import Path

from app.risk.engine import RiskGate
from tests.market_evaluation_support import full_technical_result
from tests.risk_gate_support import default_account_snapshot, default_candidates_for, default_config
from tests.policy_gate_support import route_judge_and_gate


def test_repeated_calls_are_identical() -> None:
    _, _, policy_result = route_judge_and_gate(technical=full_technical_result())
    gate = RiskGate()
    snapshot = default_account_snapshot()
    config = default_config()
    candidates = default_candidates_for(policy_result)
    first = gate.evaluate(
        strategy_policy_result=policy_result, account_snapshot=snapshot, candidate_inputs=candidates, trading_cycle_config=config
    )
    second = gate.evaluate(
        strategy_policy_result=policy_result, account_snapshot=snapshot, candidate_inputs=candidates, trading_cycle_config=config
    )
    assert first == second


def test_repeated_calls_on_empty_policy_result_are_identical() -> None:
    _, _, policy_result = route_judge_and_gate()
    gate = RiskGate()
    snapshot = default_account_snapshot()
    config = default_config()
    first = gate.evaluate(strategy_policy_result=policy_result, account_snapshot=snapshot, candidate_inputs=(), trading_cycle_config=config)
    second = gate.evaluate(strategy_policy_result=policy_result, account_snapshot=snapshot, candidate_inputs=(), trading_cycle_config=config)
    assert first == second


def test_source_has_no_wall_clock_random_or_uuid_calls() -> None:
    for module_path in (Path(inspect.getfile(RiskGate)),):
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        forbidden_attrs = {"now", "utcnow", "today"}
        forbidden_modules = {"random", "uuid", "secrets", "time"}

        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = (alias.name for alias in node.names)
                module = getattr(node, "module", None)
                offending = forbidden_modules & set(names)
                if module in forbidden_modules:
                    offending.add(module)
                assert not offending, f"{module_path.name} imports forbidden module(s): {offending}"
            if isinstance(node, ast.Attribute) and node.attr in forbidden_attrs:
                raise AssertionError(f"{module_path.name} calls a wall-clock method: .{node.attr}(...)")


def test_no_float_used_for_monetary_fields() -> None:
    _, _, policy_result = route_judge_and_gate(technical=full_technical_result())
    result = RiskGate().evaluate(
        strategy_policy_result=policy_result,
        account_snapshot=default_account_snapshot(),
        candidate_inputs=default_candidates_for(policy_result),
        trading_cycle_config=default_config(),
    )
    for family_result in result.family_results:
        assert family_result.max_individual_risk is None or isinstance(family_result.max_individual_risk, Decimal)
        assert family_result.recommended_units is None or isinstance(family_result.recommended_units, Decimal)
