"""Final Recommendation account-currency tests.

``account_currency`` is an explicit, caller-supplied passthrough of the
already-existing, unmodified ``MT5AccountFacts.currency`` - never hardcoded,
never uppercased/lowercased/converted, never FX-adjusted. Proves the same
monetary ``Decimal`` values are produced regardless of which currency label
is supplied, and that the production module contains no hardcoded currency
literal or FX/rate-lookup logic.
"""

from __future__ import annotations

import inspect

import pytest

import app.orchestration.final_recommendation as final_recommendation_module
from app.core.enums.strategy_router import StrategyFamily
from app.orchestration.final_recommendation import construct_final_recommendations
from tests.final_recommendation_support import NOW, actionable_trend_market_structure, run_pipeline, symbol_facts, trend_following_technical


def _actionable_pipeline_result():
    return run_pipeline(technical=trend_following_technical(), m15_market_structure=actionable_trend_market_structure())


@pytest.mark.parametrize("currency", ["USD", "EUR", "DKK", "XAG"])
def test_account_currency_passed_unchanged(currency: str) -> None:
    result = construct_final_recommendations(
        decision_risk_pipeline_result=_actionable_pipeline_result(),
        symbol_facts=symbol_facts(),
        account_currency=currency,
        trade_ids={StrategyFamily.TREND_FOLLOWING: "trade-1"},
        as_of=NOW,
    )
    trend = next(r for r in result.family_results if r.family is StrategyFamily.TREND_FOLLOWING)
    assert trend.recommendation.account_currency == currency


def test_changing_only_account_currency_does_not_change_monetary_values() -> None:
    pipeline_result = _actionable_pipeline_result()
    usd_result = construct_final_recommendations(
        decision_risk_pipeline_result=pipeline_result,
        symbol_facts=symbol_facts(),
        account_currency="USD",
        trade_ids={StrategyFamily.TREND_FOLLOWING: "trade-1"},
        as_of=NOW,
    )
    dkk_result = construct_final_recommendations(
        decision_risk_pipeline_result=pipeline_result,
        symbol_facts=symbol_facts(),
        account_currency="DKK",
        trade_ids={StrategyFamily.TREND_FOLLOWING: "trade-1"},
        as_of=NOW,
    )
    usd_trend = next(r for r in usd_result.family_results if r.family is StrategyFamily.TREND_FOLLOWING)
    dkk_trend = next(r for r in dkk_result.family_results if r.family is StrategyFamily.TREND_FOLLOWING)

    assert usd_trend.recommendation.approved_risk_amount == dkk_trend.recommendation.approved_risk_amount
    assert usd_trend.recommendation.approved_volume == dkk_trend.recommendation.approved_volume
    assert usd_trend.recommendation.entry_price == dkk_trend.recommendation.entry_price
    assert usd_trend.recommendation.stop_loss == dkk_trend.recommendation.stop_loss
    assert usd_trend.recommendation.account_currency != dkk_trend.recommendation.account_currency


def test_no_hardcoded_production_currency() -> None:
    source = inspect.getsource(final_recommendation_module)
    for forbidden in ('"USD"', '"EUR"', '"DKK"', "'USD'", "'EUR'", "'DKK'"):
        assert forbidden not in source


def test_no_fx_conversion_or_rate_lookup() -> None:
    source = inspect.getsource(final_recommendation_module).lower()
    for forbidden in ("exchange_rate", "fx_rate", "convert_currency", "rate_lookup", "forex"):
        assert forbidden not in source
