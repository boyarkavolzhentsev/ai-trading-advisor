"""Stage 6A ``StrategyRouter`` is a pure, deterministic function of its
input: same ``MarketEvaluationResult`` in twice must yield byte-identical
``StrategyRouterResult`` output, and the implementation must never touch the
wall clock, ``random``, or ``uuid``.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from app.strategies.router import StrategyRouter
from tests.market_evaluation_support import full_flow_result, full_technical_result, make_context
from tests.strategy_router_support import evaluation, external_result_matched


def test_repeated_calls_are_identical() -> None:
    market_evaluation = evaluation(
        technical=full_technical_result(),
        flow=full_flow_result(),
        external=external_result_matched(),
        context=make_context(),
    )
    router = StrategyRouter()
    first = router.route(market_evaluation=market_evaluation)
    second = router.route(market_evaluation=market_evaluation)
    assert first == second


def test_repeated_calls_on_empty_evaluation_are_identical() -> None:
    market_evaluation = evaluation()
    router = StrategyRouter()
    assert router.route(market_evaluation=market_evaluation) == router.route(market_evaluation=market_evaluation)


def test_source_has_no_wall_clock_random_or_uuid_calls() -> None:
    path = Path(inspect.getfile(StrategyRouter))
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
            assert not offending, f"router.py imports forbidden module(s): {offending}"
        if isinstance(node, ast.Attribute) and node.attr in forbidden_attrs:
            raise AssertionError(f"router.py calls a wall-clock method: .{node.attr}(...)")
