"""Stage 6C ``PolicyGate`` is a pure, deterministic function of its input:
same ``StrategyJudgeResult`` in twice must yield byte-identical
``StrategyPolicyResult`` output, and the implementation must never touch the
wall clock, ``random``, or ``uuid``."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from app.decision.gate import PolicyGate
from app.judge.judge import Judge
from tests.market_evaluation_support import full_flow_result, full_technical_result, make_context
from tests.strategy_judge_support import external_with_news_sentiment
from tests.strategy_router_support import evaluation
from app.strategies.router import StrategyRouter


def test_repeated_calls_are_identical() -> None:
    router_result = StrategyRouter().route(
        market_evaluation=evaluation(
            technical=full_technical_result(),
            flow=full_flow_result(),
            external=external_with_news_sentiment(provider_signs={"p1": "POSITIVE", "p2": "POSITIVE"}),
            context=make_context(),
        )
    )
    judge_result = Judge().judge(strategy_router_result=router_result)
    gate = PolicyGate()
    first = gate.apply(strategy_judge_result=judge_result)
    second = gate.apply(strategy_judge_result=judge_result)
    assert first == second


def test_repeated_calls_on_empty_judge_result_are_identical() -> None:
    router_result = StrategyRouter().route(market_evaluation=evaluation())
    judge_result = Judge().judge(strategy_router_result=router_result)
    gate = PolicyGate()
    assert gate.apply(strategy_judge_result=judge_result) == gate.apply(strategy_judge_result=judge_result)


def test_source_has_no_wall_clock_random_or_uuid_calls() -> None:
    path = Path(inspect.getfile(PolicyGate))
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
            assert not offending, f"gate.py imports forbidden module(s): {offending}"
        if isinstance(node, ast.Attribute) and node.attr in forbidden_attrs:
            raise AssertionError(f"gate.py calls a wall-clock method: .{node.attr}(...)")
