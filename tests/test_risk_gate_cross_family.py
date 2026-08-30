"""Stage 7: each Policy-eligible family is risk-gated independently against
the same ``AccountRiskSnapshot`` - no budget reservation/sequencing between
family results, no ranking/winner/voting, no direction inspection, and the
3+-candidate shared-budget case is never asserted jointly deployable."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from app.core.enums.risk_gate import RiskFamilyVerdict
from app.core.enums.strategy_router import StrategyFamily
from app.risk.engine import RiskGate
from tests.market_evaluation_support import full_flow_result, full_technical_result, make_context
from tests.policy_gate_support import route_judge_and_gate
from tests.risk_gate_support import default_account_snapshot, default_candidates_for, default_config
from tests.strategy_judge_support import external_with_news_sentiment


def _technical_with_trend_and_confirmed_break():
    """TREND analyst clean/directional UPWARD; MARKET_STRUCTURE analyst
    confirms an UPWARD_BREAK on the same timeframes - both TREND_FOLLOWING
    and BREAKOUT resolve DIRECTIONAL, non-conflicting."""
    from app.core.enums.technical_analysis import TechnicalAnalysisDimension, TechnicalAnalystType
    from app.technical_supervisor.supervisor import TechnicalSupervisor
    from tests.technical_supervisor_support import DEFAULT_TIMEFRAMES, analyzed_result, make_observation

    timeframes = DEFAULT_TIMEFRAMES[:2]
    trend_results = [
        analyzed_result(
            TechnicalAnalystType.TREND,
            timeframe,
            observations=(make_observation(dimension=TechnicalAnalysisDimension.RETURN_DIRECTION, value="UPWARD"),),
        )
        for timeframe in timeframes
    ]
    structure_results = [
        analyzed_result(
            TechnicalAnalystType.MARKET_STRUCTURE,
            timeframe,
            observations=(
                make_observation(dimension=TechnicalAnalysisDimension.STRUCTURAL_BREAK_PRESENCE, value="BREAK_CONFIRMED"),
                make_observation(dimension=TechnicalAnalysisDimension.LATEST_BREAK_DIRECTION, value="UPWARD_BREAK"),
            ),
        )
        for timeframe in timeframes
    ]
    return TechnicalSupervisor().aggregate(tuple(trend_results + structure_results))


def _all_three_eligible_risk_result(risk_per_unit=None):
    from decimal import Decimal

    _, judge_result, policy_result = route_judge_and_gate(
        technical=_technical_with_trend_and_confirmed_break(),
        flow=full_flow_result(),
        external=external_with_news_sentiment(provider_signs={"p1": "POSITIVE", "p2": "POSITIVE"}),
        context=make_context(),
    )
    rpu = risk_per_unit if risk_per_unit is not None else Decimal("10")
    candidates = default_candidates_for(policy_result, risk_per_unit=rpu)
    risk_result = RiskGate().evaluate(
        strategy_policy_result=policy_result,
        account_snapshot=default_account_snapshot(),
        candidate_inputs=candidates,
        trading_cycle_config=default_config(),
    )
    return judge_result, policy_result, risk_result


def test_three_simultaneously_eligible_families_independent_ceilings() -> None:
    judge_result, policy_result, risk_result = _all_three_eligible_risk_result()
    eligible = [r for r in risk_result.family_results if r.verdict is RiskFamilyVerdict.ELIGIBLE_FOR_PORTFOLIO_REVIEW]
    assert len(eligible) == 3
    # Each independently shows the full per-trade budget (500), even though
    # 3 x 500 = 1500 would exceed the account's daily capacity if summed -
    # Stage 7 never asserts joint deployability.
    from decimal import Decimal

    for result in eligible:
        assert result.max_individual_risk == Decimal("500.000")


def test_no_sequential_budget_reservation() -> None:
    """Evaluating with one eligible family vs three eligible families
    produces the identical max_individual_risk for TREND_FOLLOWING - proving
    no other candidate's presence reduces it (no reservation/sequencing)."""
    from decimal import Decimal

    _, _, single_risk_result = route_judge_gate_and_risk_single()
    _, _, three_risk_result = _all_three_eligible_risk_result()

    single_trend = next(r for r in single_risk_result.family_results if r.family is StrategyFamily.TREND_FOLLOWING)
    three_trend = next(r for r in three_risk_result.family_results if r.family is StrategyFamily.TREND_FOLLOWING)
    assert single_trend.max_individual_risk == three_trend.max_individual_risk == Decimal("500.000")


def route_judge_gate_and_risk_single():
    from tests.risk_gate_support import route_judge_gate_and_risk

    policy_result, risk_result = route_judge_gate_and_risk(technical=full_technical_result())
    return None, policy_result, risk_result


def test_same_direction_families_independently_eligible() -> None:
    judge_result, _, risk_result = _all_three_eligible_risk_result()
    directions = {r.family: r.direction for r in judge_result.family_results}
    assert directions[StrategyFamily.TREND_FOLLOWING] == directions[StrategyFamily.EVENT_DRIVEN]
    verdicts = {r.family: r.verdict for r in risk_result.family_results}
    assert verdicts[StrategyFamily.TREND_FOLLOWING] is RiskFamilyVerdict.ELIGIBLE_FOR_PORTFOLIO_REVIEW
    assert verdicts[StrategyFamily.EVENT_DRIVEN] is RiskFamilyVerdict.ELIGIBLE_FOR_PORTFOLIO_REVIEW


def test_opposite_direction_families_independently_eligible() -> None:
    from decimal import Decimal

    _, judge_result, policy_result = route_judge_and_gate(
        technical=full_technical_result(),
        flow=full_flow_result(),
        external=external_with_news_sentiment(provider_signs={"p1": "NEGATIVE", "p2": "NEGATIVE"}),
        context=make_context(),
    )
    candidates = default_candidates_for(policy_result, risk_per_unit=Decimal("10"))
    risk_result = RiskGate().evaluate(
        strategy_policy_result=policy_result,
        account_snapshot=default_account_snapshot(),
        candidate_inputs=candidates,
        trading_cycle_config=default_config(),
    )
    directions = {r.family: r.direction for r in judge_result.family_results}
    assert directions[StrategyFamily.TREND_FOLLOWING] != directions[StrategyFamily.EVENT_DRIVEN]
    verdicts = {r.family: r.verdict for r in risk_result.family_results}
    assert verdicts[StrategyFamily.TREND_FOLLOWING] is RiskFamilyVerdict.ELIGIBLE_FOR_PORTFOLIO_REVIEW
    assert verdicts[StrategyFamily.EVENT_DRIVEN] is RiskFamilyVerdict.ELIGIBLE_FOR_PORTFOLIO_REVIEW


def test_source_has_no_ranking_voting_or_direction_access() -> None:
    path = Path(inspect.getfile(RiskGate))
    tree = ast.parse(path.read_text(encoding="utf-8"))
    forbidden_call_names = {"Counter", "sorted", "sum"}
    forbidden_attrs = {"count", "direction", "value"}
    forbidden_identifiers = {"vote", "votes", "majority", "weight", "weights", "rank", "ranking", "score", "confidence"}

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in forbidden_call_names:
                raise AssertionError(f"engine.py calls forbidden aggregation construct: {func.id}(...)")
            if isinstance(func, ast.Attribute) and func.attr in forbidden_attrs:
                raise AssertionError(f"engine.py calls forbidden .{func.attr}(...)")
        if isinstance(node, ast.Attribute) and node.attr in forbidden_attrs:
            raise AssertionError(f"engine.py accesses forbidden attribute .{node.attr}")
        if isinstance(node, ast.Name) and node.id in forbidden_identifiers:
            raise AssertionError(f"engine.py uses forbidden identifier name {node.id!r}")
