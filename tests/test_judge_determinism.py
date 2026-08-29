"""Stage 6B ``Judge`` is a pure, deterministic function of its input: same
``StrategyRouterResult`` in twice must yield byte-identical
``StrategyJudgeResult`` output, and the implementation must never touch the
wall clock, ``random``, or ``uuid``."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from app.judge.judge import Judge
from tests.market_evaluation_support import full_flow_result, full_technical_result, make_context
from tests.strategy_judge_support import external_with_news_sentiment, route_and_judge


def test_repeated_calls_are_identical() -> None:
    router_result, _ = route_and_judge(
        technical=full_technical_result(),
        flow=full_flow_result(),
        external=external_with_news_sentiment(provider_signs={"p1": "POSITIVE", "p2": "POSITIVE"}),
        context=make_context(),
    )
    judge = Judge()
    first = judge.judge(strategy_router_result=router_result)
    second = judge.judge(strategy_router_result=router_result)
    assert first == second


def test_repeated_calls_on_empty_evaluation_are_identical() -> None:
    router_result, _ = route_and_judge()
    judge = Judge()
    assert judge.judge(strategy_router_result=router_result) == judge.judge(strategy_router_result=router_result)


def test_source_has_no_wall_clock_random_or_uuid_calls() -> None:
    path = Path(inspect.getfile(Judge))
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
            assert not offending, f"judge.py imports forbidden module(s): {offending}"
        if isinstance(node, ast.Attribute) and node.attr in forbidden_attrs:
            raise AssertionError(f"judge.py calls a wall-clock method: .{node.attr}(...)")
