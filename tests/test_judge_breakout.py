"""Stage 6B BREAKOUT semantic rules: STRUCTURAL_BREAK_PRESENCE +
LATEST_BREAK_DIRECTION coherence as PRIMARY, RETURN_DIRECTION coherence as
veto-only CORROBORATING - Technical only. Flow content must have zero
effect, and BREAKOUT must never be judged when Router marked it ineligible."""

from __future__ import annotations

from app.core.enums.flow_analysis import AnalystType as FlowAnalystType
from app.core.enums.quality import FeatureQuality
from app.core.enums.strategy_judge import DirectionalCandidate, JudgeOutcome
from app.core.enums.strategy_router import StrategyFamily
from app.flow_supervisor.supervisor import FlowSupervisor
from tests.flow_supervisor_support import analyzed_result as flow_analyzed_result
from tests.market_evaluation_support import full_flow_result
from tests.strategy_judge_support import route_and_judge, technical_with_market_structure_break


def _breakout_result(judge_result):
    matches = [r for r in judge_result.family_results if r.family is StrategyFamily.BREAKOUT]
    return matches[0] if matches else None


def test_confirmed_upward_break_is_directional_long() -> None:
    technical = technical_with_market_structure_break(break_direction="UPWARD_BREAK")
    _, judge_result = route_and_judge(technical=technical, flow=full_flow_result())
    result = _breakout_result(judge_result)
    assert result.outcome is JudgeOutcome.DIRECTIONAL
    assert result.direction is DirectionalCandidate.LONG_CANDIDATE


def test_confirmed_downward_break_is_directional_short() -> None:
    technical = technical_with_market_structure_break(break_direction="DOWNWARD_BREAK")
    _, judge_result = route_and_judge(technical=technical, flow=full_flow_result())
    result = _breakout_result(judge_result)
    assert result.outcome is JudgeOutcome.DIRECTIONAL
    assert result.direction is DirectionalCandidate.SHORT_CANDIDATE


def test_return_direction_veto_forces_mixed() -> None:
    technical = technical_with_market_structure_break(break_direction="UPWARD_BREAK", return_direction="DOWNWARD")
    _, judge_result = route_and_judge(technical=technical, flow=full_flow_result())
    result = _breakout_result(judge_result)
    assert result.outcome is JudgeOutcome.MIXED
    assert result.direction is None


def test_agreeing_return_direction_stays_directional() -> None:
    technical = technical_with_market_structure_break(break_direction="UPWARD_BREAK", return_direction="UPWARD")
    _, judge_result = route_and_judge(technical=technical, flow=full_flow_result())
    result = _breakout_result(judge_result)
    assert result.outcome is JudgeOutcome.DIRECTIONAL
    assert result.direction is DirectionalCandidate.LONG_CANDIDATE


def test_no_confirmed_break_is_insufficient() -> None:
    technical = technical_with_market_structure_break(break_confirmed=False, break_direction=None)
    _, judge_result = route_and_judge(technical=technical, flow=full_flow_result())
    result = _breakout_result(judge_result)
    assert result.outcome is JudgeOutcome.INSUFFICIENT_EVIDENCE
    assert result.direction is None
    assert result.evidence_refs == ()


def test_flow_content_has_zero_effect_on_breakout_result() -> None:
    """Vary Flow's own semantic content arbitrarily while holding Technical
    fixed - the Judge BREAKOUT result must be byte-identical regardless."""
    technical = technical_with_market_structure_break(break_direction="UPWARD_BREAK")

    flow_bullish = full_flow_result()
    flow_bearish = FlowSupervisor().aggregate((flow_analyzed_result(FlowAnalystType.TAKER_FLOW, quality=FeatureQuality.VALID),))

    _, judge_bullish = route_and_judge(technical=technical, flow=flow_bullish)
    _, judge_bearish = route_and_judge(technical=technical, flow=flow_bearish)

    assert _breakout_result(judge_bullish) == _breakout_result(judge_bearish)


def test_breakout_ineligible_at_router_is_never_judged() -> None:
    """Flow missing entirely - Router marks BREAKOUT ineligible, so Judge
    must never produce a result for it, even with a strong confirmed break."""
    technical = technical_with_market_structure_break(break_direction="UPWARD_BREAK")
    router_result, judge_result = route_and_judge(technical=technical)
    assert StrategyFamily.BREAKOUT not in router_result.eligible_families
    assert _breakout_result(judge_result) is None
