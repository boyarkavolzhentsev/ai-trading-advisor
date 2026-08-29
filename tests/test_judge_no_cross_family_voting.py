"""Stage 6B: each eligible family is judged independently - no family's
outcome may influence another's, and no majority/vote counting exists
anywhere in the implementation."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from app.core.enums.strategy_judge import JudgeOutcome
from app.core.enums.strategy_router import StrategyFamily
from app.judge.judge import Judge
from tests.market_evaluation_support import full_flow_result, full_technical_result, make_context
from tests.strategy_judge_support import external_with_news_sentiment, route_and_judge


def test_conflicting_families_do_not_influence_each_other() -> None:
    """TREND_FOLLOWING strongly LONG, EVENT_DRIVEN strongly SHORT in the
    same evaluation - each family's own outcome/direction is unaffected by
    the other's."""
    _, judge_result = route_and_judge(
        technical=full_technical_result(),
        flow=full_flow_result(),
        external=external_with_news_sentiment(provider_signs={"p1": "NEGATIVE", "p2": "NEGATIVE"}),
        context=make_context(),
    )
    outcomes = {result.family: result for result in judge_result.family_results}
    trend = outcomes[StrategyFamily.TREND_FOLLOWING]
    event = outcomes[StrategyFamily.EVENT_DRIVEN]
    assert trend.outcome is JudgeOutcome.DIRECTIONAL
    assert event.outcome is JudgeOutcome.DIRECTIONAL
    # Independently derived - no shared/overlapping evidence refs.
    trend_refs = {(r.contour, r.analyst_result_index, r.observation_index) for r in trend.evidence_refs}
    event_refs = {(r.contour, r.analyst_result_index, r.observation_index) for r in event.evidence_refs}
    assert trend_refs.isdisjoint(event_refs)


def test_source_has_no_vote_or_count_based_aggregation() -> None:
    source = Path(inspect.getfile(Judge)).read_text(encoding="utf-8")
    for forbidden in ("Counter(", ".count(", "sum(", "vote", "majority", "weight"):
        assert forbidden not in source, f"judge.py contains a forbidden aggregation construct: {forbidden!r}"
