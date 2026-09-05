"""Final Recommendation trade_id ownership tests.

``trade_id`` is inert, caller-supplied data only - this module never
generates, derives, or infers one. Proves: exact preservation, a missing
required entry raises a caller-contract exception (never a fabricated ID or
a business block reason), a session-blocked family never needs one, and no
nondeterministic ID generation appears in the production module's source.
"""

from __future__ import annotations

import ast
import inspect

import pytest

from app.core.enums.final_recommendation import FinalRecommendationVerdict
from app.core.enums.strategy_router import StrategyFamily
import app.orchestration.final_recommendation as final_recommendation_module
from app.orchestration.errors import MissingTradeIdForActionableFamilyError
from app.orchestration.final_recommendation import construct_final_recommendations
from tests.final_recommendation_support import NOW, actionable_trend_market_structure, run_pipeline, symbol_facts, trend_following_technical


def _actionable_pipeline_result():
    return run_pipeline(technical=trend_following_technical(), m15_market_structure=actionable_trend_market_structure())


def test_caller_supplied_trade_id_preserved_exactly() -> None:
    result = construct_final_recommendations(
        decision_risk_pipeline_result=_actionable_pipeline_result(),
        symbol_facts=symbol_facts(),
        account_currency="USD",
        trade_ids={StrategyFamily.TREND_FOLLOWING: "operator-supplied-id-42"},
        as_of=NOW,
    )
    trend = next(r for r in result.family_results if r.family is StrategyFamily.TREND_FOLLOWING)
    assert trend.verdict is FinalRecommendationVerdict.ACTIONABLE
    assert trend.recommendation.trade_id == "operator-supplied-id-42"


def test_missing_required_trade_id_raises_contract_error() -> None:
    with pytest.raises(MissingTradeIdForActionableFamilyError):
        construct_final_recommendations(
            decision_risk_pipeline_result=_actionable_pipeline_result(),
            symbol_facts=symbol_facts(),
            account_currency="USD",
            trade_ids={},
            as_of=NOW,
        )


def test_blocked_family_does_not_require_trade_id() -> None:
    """A far stop makes Stage 10C ``BELOW_BROKER_MINIMUM_VOLUME`` - the
    family never becomes ACTIONABLE, so no ``trade_ids`` entry is needed."""
    from tests.decision_risk_pipeline_support import trend_following_market_structure as far_market_structure

    pipeline_result = run_pipeline(technical=trend_following_technical(), m15_market_structure=far_market_structure())
    result = construct_final_recommendations(
        decision_risk_pipeline_result=pipeline_result,
        symbol_facts=symbol_facts(),
        account_currency="USD",
        trade_ids={},
        as_of=NOW,
    )
    trend = next(r for r in result.family_results if r.family is StrategyFamily.TREND_FOLLOWING)
    assert trend.verdict is FinalRecommendationVerdict.BLOCKED


def test_no_internal_id_generation() -> None:
    source = inspect.getsource(final_recommendation_module)
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in {"now", "utcnow", "today", "uuid4"}, "must not read wall clock/generate UUIDs"
        if isinstance(node, ast.Name):
            assert node.id not in {"random", "uuid"}, f"must not reference {node.id}"
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    assert imports.isdisjoint({"uuid", "random"})
