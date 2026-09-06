"""Tracking Integration / provenance account-currency tests (Final Runtime
Integration, Part E corrective design).

``account_currency`` is an explicit, caller-supplied passthrough of
``FinalRecommendation.account_currency`` (itself the already-existing,
unmodified ``MT5AccountFacts.currency``) - never hardcoded, never converted,
never FX-adjusted, and never consulted by matching/lifecycle business logic.
"""

from __future__ import annotations

import inspect

import pytest

import app.mt5.recommendation_provenance_persistence as provenance_persistence_module
import app.orchestration.tracking_integration as tracking_integration_module
from app.core.enums.market import MarketType
from app.core.enums.strategy_router import StrategyFamily
from app.orchestration.final_recommendation import construct_final_recommendations
from app.orchestration.tracking_integration import construct_tracked_recommendations
from tests.final_recommendation_support import NOW, actionable_trend_market_structure, run_pipeline, symbol_facts, trend_following_technical


def _final_recommendation_result(currency: str):
    pipeline_result = run_pipeline(technical=trend_following_technical(), m15_market_structure=actionable_trend_market_structure())
    return construct_final_recommendations(
        decision_risk_pipeline_result=pipeline_result,
        symbol_facts=symbol_facts(),
        account_currency=currency,
        trade_ids={StrategyFamily.TREND_FOLLOWING: "trade-1"},
        as_of=NOW,
    )


@pytest.mark.parametrize("currency", ["USD", "EUR", "DKK", "XAG"])
def test_account_currency_passed_unchanged_into_provenance(currency: str) -> None:
    final_result = _final_recommendation_result(currency)
    results = construct_tracked_recommendations(
        final_recommendation_construction_result=final_result,
        as_of=NOW,
        market=MarketType.FX,
        pre_existing_positions_read_status="OK",
        pre_existing_positions=(),
    )
    assert results[0].provenance.account_currency == currency


def test_changing_only_account_currency_does_not_change_monetary_values() -> None:
    usd_result = construct_tracked_recommendations(
        final_recommendation_construction_result=_final_recommendation_result("USD"),
        as_of=NOW,
        market=MarketType.FX,
        pre_existing_positions_read_status="OK",
        pre_existing_positions=(),
    )
    dkk_result = construct_tracked_recommendations(
        final_recommendation_construction_result=_final_recommendation_result("DKK"),
        as_of=NOW,
        market=MarketType.FX,
        pre_existing_positions_read_status="OK",
        pre_existing_positions=(),
    )
    assert usd_result[0].provenance.approved_risk_amount == dkk_result[0].provenance.approved_risk_amount
    usd_tracked = usd_result[0].tracking_creation_result.tracked_recommendation
    dkk_tracked = dkk_result[0].tracking_creation_result.tracked_recommendation
    assert usd_tracked.approved_broker_volume == dkk_tracked.approved_broker_volume
    assert usd_tracked.position_record.planned_entry == dkk_tracked.position_record.planned_entry
    assert usd_result[0].provenance.account_currency != dkk_result[0].provenance.account_currency


def test_no_hardcoded_production_currency() -> None:
    for module in (tracking_integration_module, provenance_persistence_module):
        source = inspect.getsource(module)
        for forbidden in ('"USD"', '"EUR"', '"DKK"', "'USD'", "'EUR'", "'DKK'"):
            assert forbidden not in source, f"{module.__name__} must not hardcode {forbidden}"


def test_no_fx_conversion_or_rate_lookup() -> None:
    for module in (tracking_integration_module, provenance_persistence_module):
        source = inspect.getsource(module).lower()
        for forbidden in ("exchange_rate", "fx_rate", "convert_currency", "rate_lookup", "forex"):
            assert forbidden not in source, f"{module.__name__} must not reference {forbidden}"


def test_account_currency_never_referenced_in_tracking_integration_matching_path() -> None:
    """Stage 10E's own ``create_tracked_recommendation`` call never receives
    ``account_currency`` - it stays pure provenance metadata, never business
    logic input."""
    source = inspect.getsource(tracking_integration_module)
    create_call_start = source.index("create_tracked_recommendation(")
    create_call_end = source.index(")", source.index("pre_existing_positions=pre_existing_positions"))
    create_call_block = source[create_call_start:create_call_end]
    assert "account_currency" not in create_call_block
    assert "approved_risk_amount" not in create_call_block
