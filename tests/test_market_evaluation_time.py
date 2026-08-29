"""Stage 5A time-consistency tests.

Each supplied contour's own semantic timestamp must be ``<= evaluation_time``
- no tolerance, no cross-contour equality requirement, no wall clock.
"""

from __future__ import annotations

import ast
import inspect
from datetime import timedelta
from pathlib import Path

import pytest

from app.market_evaluation import errors, evaluator, protocols
from app.market_evaluation.errors import FutureContourTimeError
from app.market_evaluation.evaluator import MarketEvaluator
from tests.market_evaluation_support import (
    NOW,
    full_external_result,
    full_flow_result,
    full_technical_result,
    make_context,
)

MODULES = (errors, evaluator, protocols)


def test_future_flow_raises() -> None:
    flow = full_flow_result(observation_time=NOW + timedelta(hours=1))
    with pytest.raises(FutureContourTimeError):
        MarketEvaluator().evaluate(flow=flow, technical=None, external=None, context=make_context(), evaluation_time=NOW)


def test_future_technical_raises() -> None:
    technical = full_technical_result(observation_time=NOW + timedelta(hours=1))
    with pytest.raises(FutureContourTimeError):
        MarketEvaluator().evaluate(
            flow=None, technical=technical, external=None, context=make_context(), evaluation_time=NOW
        )


def test_future_external_raises() -> None:
    external = full_external_result(analysis_time=NOW + timedelta(hours=1))
    with pytest.raises(FutureContourTimeError):
        MarketEvaluator().evaluate(
            flow=None, technical=None, external=external, context=make_context(), evaluation_time=NOW
        )


def test_equal_timestamps_are_accepted() -> None:
    flow = full_flow_result(observation_time=NOW)
    technical = full_technical_result(observation_time=NOW)
    external = full_external_result(analysis_time=NOW)
    result = MarketEvaluator().evaluate(
        flow=flow, technical=technical, external=external, context=make_context(), evaluation_time=NOW
    )
    assert result.evaluation_time == NOW


def test_older_timestamps_are_accepted() -> None:
    earlier = NOW - timedelta(hours=1)
    flow = full_flow_result(observation_time=earlier)
    technical = full_technical_result(observation_time=earlier)
    external = full_external_result(analysis_time=earlier)
    result = MarketEvaluator().evaluate(
        flow=flow, technical=technical, external=external, context=make_context(), evaluation_time=NOW
    )
    assert result.evaluation_time == NOW


def test_contours_need_not_share_the_same_timestamp() -> None:
    flow = full_flow_result(observation_time=NOW - timedelta(hours=2))
    technical = full_technical_result(observation_time=NOW - timedelta(minutes=5))
    external = full_external_result(analysis_time=NOW)
    result = MarketEvaluator().evaluate(
        flow=flow, technical=technical, external=external, context=make_context(), evaluation_time=NOW
    )
    assert result.flow.observation_time != result.technical.observation_time


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_no_wall_clock_usage(module) -> None:
    source = Path(inspect.getfile(module)).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in {"now", "utcnow", "today"}:
            pytest.fail(f"{module.__name__} calls a wall-clock method: .{node.attr}")
