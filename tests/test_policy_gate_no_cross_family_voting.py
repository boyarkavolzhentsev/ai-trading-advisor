"""Stage 6C: each Router-eligible family is policy-gated independently - no
family's verdict may influence another's, and no majority/vote/ranking
construct exists anywhere in the implementation."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from app.core.enums.policy_gate import PolicyFamilyVerdict
from app.core.enums.quality import FeatureQuality
from app.core.enums.strategy_judge import JudgeOutcome
from app.core.enums.strategy_router import StrategyFamily
from app.core.enums.technical_analysis import TechnicalAnalysisDimension, TechnicalAnalystType
from app.decision.gate import PolicyGate
from app.technical_supervisor.supervisor import TechnicalSupervisor
from tests.market_evaluation_support import full_flow_result, full_technical_result, make_context
from tests.policy_gate_support import route_judge_and_gate, technical_trend_with_quality
from tests.strategy_judge_support import external_with_news_sentiment
from tests.technical_supervisor_support import DEFAULT_TIMEFRAMES, analyzed_result, make_observation


def test_same_direction_families_independently_eligible() -> None:
    _, judge_result, policy_result = route_judge_and_gate(
        technical=full_technical_result(),
        flow=full_flow_result(),
        external=external_with_news_sentiment(provider_signs={"p1": "POSITIVE", "p2": "POSITIVE"}),
        context=make_context(),
    )
    directions = {r.family: r.direction for r in judge_result.family_results}
    assert directions[StrategyFamily.TREND_FOLLOWING] == directions[StrategyFamily.EVENT_DRIVEN]
    verdicts = {r.family: r.verdict for r in policy_result.family_results}
    assert verdicts[StrategyFamily.TREND_FOLLOWING] is PolicyFamilyVerdict.ELIGIBLE_FOR_RISK_REVIEW
    assert verdicts[StrategyFamily.EVENT_DRIVEN] is PolicyFamilyVerdict.ELIGIBLE_FOR_RISK_REVIEW


def test_opposite_direction_families_independently_eligible() -> None:
    """TREND_FOLLOWING LONG_CANDIDATE, EVENT_DRIVEN SHORT_CANDIDATE, both
    quality-clean - both remain ELIGIBLE_FOR_RISK_REVIEW, no conflict flag,
    no suppression."""
    _, judge_result, policy_result = route_judge_and_gate(
        technical=full_technical_result(),
        flow=full_flow_result(),
        external=external_with_news_sentiment(provider_signs={"p1": "NEGATIVE", "p2": "NEGATIVE"}),
        context=make_context(),
    )
    outcomes = {r.family: r for r in judge_result.family_results}
    assert outcomes[StrategyFamily.TREND_FOLLOWING].outcome is JudgeOutcome.DIRECTIONAL
    assert outcomes[StrategyFamily.EVENT_DRIVEN].outcome is JudgeOutcome.DIRECTIONAL
    assert outcomes[StrategyFamily.TREND_FOLLOWING].direction != outcomes[StrategyFamily.EVENT_DRIVEN].direction

    verdicts = {r.family: r for r in policy_result.family_results}
    assert verdicts[StrategyFamily.TREND_FOLLOWING].verdict is PolicyFamilyVerdict.ELIGIBLE_FOR_RISK_REVIEW
    assert verdicts[StrategyFamily.EVENT_DRIVEN].verdict is PolicyFamilyVerdict.ELIGIBLE_FOR_RISK_REVIEW
    # No field anywhere carries a cross-family conflict signal.
    assert "confidence" not in type(verdicts[StrategyFamily.TREND_FOLLOWING]).model_fields


def test_one_directional_one_mixed_handled_independently() -> None:
    """TREND analyst clean/directional; MARKET_STRUCTURE analyst carries a
    conflicting LATEST_BREAK_DIRECTION across timeframes, forcing BREAKOUT
    to MIXED - TREND_FOLLOWING's own verdict must be unaffected."""
    trend_results = [
        analyzed_result(
            TechnicalAnalystType.TREND,
            timeframe,
            observations=(make_observation(dimension=TechnicalAnalysisDimension.RETURN_DIRECTION, value="UPWARD"),),
        )
        for timeframe in DEFAULT_TIMEFRAMES[:2]
    ]
    structure_results = [
        analyzed_result(
            TechnicalAnalystType.MARKET_STRUCTURE,
            DEFAULT_TIMEFRAMES[0],
            observations=(
                make_observation(dimension=TechnicalAnalysisDimension.STRUCTURAL_BREAK_PRESENCE, value="BREAK_CONFIRMED"),
                make_observation(dimension=TechnicalAnalysisDimension.LATEST_BREAK_DIRECTION, value="UPWARD_BREAK"),
            ),
        ),
        analyzed_result(
            TechnicalAnalystType.MARKET_STRUCTURE,
            DEFAULT_TIMEFRAMES[1],
            observations=(
                make_observation(dimension=TechnicalAnalysisDimension.STRUCTURAL_BREAK_PRESENCE, value="BREAK_CONFIRMED"),
                make_observation(dimension=TechnicalAnalysisDimension.LATEST_BREAK_DIRECTION, value="DOWNWARD_BREAK"),
            ),
        ),
    ]
    technical = TechnicalSupervisor().aggregate(tuple(trend_results + structure_results))
    _, judge_result, policy_result = route_judge_and_gate(technical=technical, flow=full_flow_result())

    outcomes = {r.family: r for r in judge_result.family_results}
    assert outcomes[StrategyFamily.TREND_FOLLOWING].outcome is JudgeOutcome.DIRECTIONAL
    assert outcomes[StrategyFamily.BREAKOUT].outcome is JudgeOutcome.MIXED

    verdicts = {r.family: r for r in policy_result.family_results}
    assert verdicts[StrategyFamily.TREND_FOLLOWING].verdict is PolicyFamilyVerdict.ELIGIBLE_FOR_RISK_REVIEW
    assert verdicts[StrategyFamily.BREAKOUT].verdict is PolicyFamilyVerdict.BLOCKED


def test_one_clean_one_stale_handled_independently() -> None:
    """TREND_FOLLOWING built from STALE evidence (blocked); EVENT_DRIVEN
    built from VALID evidence (eligible) - independent verdicts."""
    _, judge_result, policy_result = route_judge_and_gate(
        technical=technical_trend_with_quality(quality=FeatureQuality.STALE),
        external=external_with_news_sentiment(provider_signs={"p1": "POSITIVE", "p2": "POSITIVE"}),
        context=make_context(),
    )
    verdicts = {r.family: r for r in policy_result.family_results}
    assert verdicts[StrategyFamily.TREND_FOLLOWING].verdict is PolicyFamilyVerdict.BLOCKED
    assert verdicts[StrategyFamily.EVENT_DRIVEN].verdict is PolicyFamilyVerdict.ELIGIBLE_FOR_RISK_REVIEW


def test_multiple_eligible_families_supported_simultaneously() -> None:
    _, _, policy_result = route_judge_and_gate(
        technical=full_technical_result(),
        flow=full_flow_result(),
        external=external_with_news_sentiment(provider_signs={"p1": "POSITIVE", "p2": "POSITIVE"}),
        context=make_context(),
    )
    eligible = [r for r in policy_result.family_results if r.verdict is PolicyFamilyVerdict.ELIGIBLE_FOR_RISK_REVIEW]
    assert len(eligible) >= 2


def test_source_has_no_vote_rank_or_count_based_aggregation() -> None:
    """AST-based, not a substring scan: a substring check would also reject
    legitimate prose (e.g. a docstring saying "no vote exists") - this
    inspects actual calls and identifier names in the code only."""
    path = Path(inspect.getfile(PolicyGate))
    tree = ast.parse(path.read_text(encoding="utf-8"))
    forbidden_call_names = {"Counter", "sorted", "sum"}
    forbidden_attrs = {"count"}
    forbidden_identifiers = {"vote", "votes", "majority", "weight", "weights", "rank", "ranking", "score", "confidence"}

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in forbidden_call_names:
                raise AssertionError(f"gate.py calls forbidden aggregation construct: {func.id}(...)")
            if isinstance(func, ast.Attribute) and func.attr in forbidden_attrs:
                raise AssertionError(f"gate.py calls forbidden .{func.attr}(...)")
        if isinstance(node, ast.Name) and node.id in forbidden_identifiers:
            raise AssertionError(f"gate.py uses forbidden identifier name {node.id!r}")
        if isinstance(node, ast.arg) and node.arg in forbidden_identifiers:
            raise AssertionError(f"gate.py uses forbidden parameter name {node.arg!r}")
