"""Stage 6B Judge must never import or read Flow dimension-vocabulary
content - Flow's structural presence remains a Router prerequisite for
BREAKOUT, but its semantic content is never interpreted in V1 (see the
approved Stage 6B design report's Flow/Technical timescale-alignment
blocker)."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from app.judge import judge, protocols

MODULES = (judge, protocols)

FORBIDDEN_MODULES = ("app.core.enums.flow_analysis", "app.flow", "app.flow_analysts", "app.flow_supervisor")


def _imports(module) -> set[str]:
    tree = ast.parse(Path(inspect.getfile(module)).read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_no_flow_module_imported(module) -> None:
    offending = {name for name in _imports(module) if name in FORBIDDEN_MODULES or name.startswith(FORBIDDEN_MODULES)}
    assert offending == set(), f"{module.__name__} imports forbidden Flow module(s): {offending}"


def test_judge_result_never_carries_a_flow_contour_ref() -> None:
    """Behavioral guard: no Judge-produced ref ever points at FLOW, across
    every approved family rule, even when Flow data is rich and present."""
    from app.core.enums.strategy_judge import JudgeContour
    from tests.market_evaluation_support import full_flow_result, full_technical_result, make_context
    from tests.strategy_judge_support import external_with_news_sentiment, route_and_judge

    _, judge_result = route_and_judge(
        technical=full_technical_result(),
        flow=full_flow_result(),
        external=external_with_news_sentiment(provider_signs={"p1": "POSITIVE", "p2": "POSITIVE"}),
        context=make_context(),
    )
    for family_result in judge_result.family_results:
        for ref in family_result.evidence_refs:
            assert ref.contour is not JudgeContour.FLOW
