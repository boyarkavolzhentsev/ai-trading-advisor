"""Final Recommendation -> Stage 10E tracking-creation integration behavioral
tests (Final Runtime Integration, Part E).

Builds real ``FinalRecommendationConstructionResult`` fixtures via the real
``construct_final_recommendations`` (never a hand-rolled result), then runs
them through the real ``construct_tracked_recommendations`` - asserting
against the exact same downstream Stage 10E contract its own test suite
already verifies independently.
"""

from __future__ import annotations

from decimal import Decimal

from app.core.enums.final_recommendation import FinalRecommendationVerdict
from app.core.enums.market import MarketType
from app.core.enums.mt5_matching import MT5TrackedRecommendationCreationOutcome
from app.core.enums.order import OrderSide
from app.core.enums.strategy_router import StrategyFamily
from app.core.enums.trade import TradeDirection
from app.core.models.mt5_position import MT5Position
from app.orchestration.final_recommendation import construct_final_recommendations
from app.orchestration.tracking_integration import construct_tracked_recommendations
from tests.final_recommendation_support import (
    NOW,
    actionable_trend_market_structure,
    opposite_direction_market_structure,
    opposite_direction_technical,
    run_pipeline,
    symbol_facts,
    trend_following_technical,
)
from tests.market_evaluation_support import full_flow_result


def _actionable_final_recommendation_result(trade_ids: dict | None = None):
    pipeline_result = run_pipeline(
        technical=trend_following_technical(), m15_market_structure=actionable_trend_market_structure()
    )
    return construct_final_recommendations(
        decision_risk_pipeline_result=pipeline_result,
        symbol_facts=symbol_facts(),
        account_currency="USD",
        trade_ids=trade_ids if trade_ids is not None else {StrategyFamily.TREND_FOLLOWING: "trade-1"},
        as_of=NOW,
    )


def _opposite_direction_final_recommendation_result():
    pipeline_result = run_pipeline(
        technical=opposite_direction_technical(),
        flow=full_flow_result(),
        m15_market_structure=opposite_direction_market_structure(),
        # a single shared Binance reference strictly between the LONG stop
        # (100) and the SHORT stop (100.10) - both directions' distance
        # translates positively (mirrors the one-shared-reference-per-cycle
        # production reality).
        binance_reference_price=Decimal("100.05"),
        symbol_facts_override=symbol_facts(bid=Decimal("100.08")),
    )
    return construct_final_recommendations(
        decision_risk_pipeline_result=pipeline_result,
        symbol_facts=symbol_facts(),
        account_currency="USD",
        trade_ids={StrategyFamily.TREND_FOLLOWING: "trade-long", StrategyFamily.BREAKOUT: "trade-short"},
        as_of=NOW,
    )


# --- A: exact FinalRecommendation -> Stage 10E mapping ---


def test_exact_field_mapping_into_stage_10e_creation() -> None:
    final_result = _actionable_final_recommendation_result()
    recommendation = next(
        r.recommendation for r in final_result.family_results if r.family is StrategyFamily.TREND_FOLLOWING
    )

    results = construct_tracked_recommendations(
        final_recommendation_construction_result=final_result,
        as_of=NOW,
        market=MarketType.FX,
        pre_existing_positions_read_status="OK",
        pre_existing_positions=(),
    )

    assert len(results) == 1
    tracked = results[0].tracking_creation_result.tracked_recommendation
    assert tracked is not None
    record = tracked.position_record
    assert record.trade_id == recommendation.trade_id
    assert record.symbol == recommendation.symbol
    assert record.direction == recommendation.direction
    assert record.planned_entry == recommendation.entry_price
    assert record.stop_loss == recommendation.stop_loss
    assert record.take_profit_levels == list(recommendation.take_profit_levels)
    assert tracked.approved_broker_volume == recommendation.approved_volume
    assert record.signal_time == recommendation.signal_time
    assert record.valid_until == recommendation.valid_until


# --- B/C: explicit MarketType passthrough, never inferred ---


def test_market_type_is_explicit_passthrough() -> None:
    final_result = _actionable_final_recommendation_result()
    results = construct_tracked_recommendations(
        final_recommendation_construction_result=final_result,
        as_of=NOW,
        market=MarketType.FX,
        pre_existing_positions_read_status="OK",
        pre_existing_positions=(),
    )
    tracked = results[0].tracking_creation_result.tracked_recommendation
    assert tracked.position_record.market is MarketType.FX


def test_market_type_never_inferred_from_symbol() -> None:
    """The symbol here is ``EURUSD`` (an FX-looking symbol) - forcing
    ``MarketType.CRYPTO`` must succeed unchanged, proving no symbol -> market
    inference table exists anywhere in this module."""
    final_result = _actionable_final_recommendation_result()
    results = construct_tracked_recommendations(
        final_recommendation_construction_result=final_result,
        as_of=NOW,
        market=MarketType.CRYPTO,
        pre_existing_positions_read_status="OK",
        pre_existing_positions=(),
    )
    tracked = results[0].tracking_creation_result.tracked_recommendation
    assert tracked.position_record.market is MarketType.CRYPTO


# --- D: trade_id preserved ---


def test_trade_id_preserved_exactly() -> None:
    final_result = _actionable_final_recommendation_result(trade_ids={StrategyFamily.TREND_FOLLOWING: "operator-42"})
    results = construct_tracked_recommendations(
        final_recommendation_construction_result=final_result,
        as_of=NOW,
        market=MarketType.FX,
        pre_existing_positions_read_status="OK",
        pre_existing_positions=(),
    )
    assert results[0].trade_id == "operator-42"
    assert results[0].tracking_creation_result.tracked_recommendation.position_record.trade_id == "operator-42"
    assert results[0].provenance.trade_id == "operator-42"


# --- E: approved_volume -> approved_broker_volume unchanged ---


def test_approved_volume_maps_to_approved_broker_volume_unchanged() -> None:
    final_result = _actionable_final_recommendation_result()
    recommendation = next(
        r.recommendation for r in final_result.family_results if r.family is StrategyFamily.TREND_FOLLOWING
    )
    results = construct_tracked_recommendations(
        final_recommendation_construction_result=final_result,
        as_of=NOW,
        market=MarketType.FX,
        pre_existing_positions_read_status="OK",
        pre_existing_positions=(),
    )
    tracked = results[0].tracking_creation_result.tracked_recommendation
    assert tracked.approved_broker_volume == recommendation.approved_volume


# --- F/G: pre-existing positions/status passed unchanged; cannot be claimed ---


def test_pre_existing_positions_snapshot_passed_unchanged() -> None:
    final_result = _actionable_final_recommendation_result()
    recommendation = next(
        r.recommendation for r in final_result.family_results if r.family is StrategyFamily.TREND_FOLLOWING
    )
    pre_existing = (
        MT5Position(
            as_of=NOW,
            ticket=555,
            symbol=recommendation.symbol,
            side=OrderSide.BUY,
            volume=Decimal("1"),
            price_open=Decimal("100"),
            price_current=Decimal("101"),
        ),
    )
    results = construct_tracked_recommendations(
        final_recommendation_construction_result=final_result,
        as_of=NOW,
        market=MarketType.FX,
        pre_existing_positions_read_status="OK",
        pre_existing_positions=pre_existing,
    )
    tracked = results[0].tracking_creation_result.tracked_recommendation
    # Exactly Stage 10E's own create_tracked_recommendation exclusion set -
    # this is the mechanism the existing, unmodified match_recommendation
    # relies on to guarantee ticket 555 can never later be claimed.
    assert tracked.pre_existing_position_ids == (555,)


def test_pre_existing_position_from_different_symbol_not_included() -> None:
    final_result = _actionable_final_recommendation_result()
    pre_existing = (
        MT5Position(
            as_of=NOW,
            ticket=999,
            symbol="OTHERPAIR",
            side=OrderSide.BUY,
            volume=Decimal("1"),
            price_open=Decimal("100"),
            price_current=Decimal("101"),
        ),
    )
    results = construct_tracked_recommendations(
        final_recommendation_construction_result=final_result,
        as_of=NOW,
        market=MarketType.FX,
        pre_existing_positions_read_status="OK",
        pre_existing_positions=pre_existing,
    )
    tracked = results[0].tracking_creation_result.tracked_recommendation
    assert tracked.pre_existing_position_ids == ()


# --- H: unavailable snapshot preserves Stage 10E SNAPSHOT_UNAVAILABLE ---


def test_unavailable_snapshot_preserves_stage_10e_fail_closed_outcome() -> None:
    final_result = _actionable_final_recommendation_result()
    results = construct_tracked_recommendations(
        final_recommendation_construction_result=final_result,
        as_of=NOW,
        market=MarketType.FX,
        pre_existing_positions_read_status="UNAVAILABLE",
        pre_existing_positions=(),
    )
    assert len(results) == 1
    assert results[0].tracking_creation_result.outcome is MT5TrackedRecommendationCreationOutcome.SNAPSHOT_UNAVAILABLE
    assert results[0].tracking_creation_result.tracked_recommendation is None
    # trade_id/provenance remain identifiable even though creation failed closed:
    assert results[0].trade_id == "trade-1"
    assert results[0].provenance.trade_id == "trade-1"


def test_unmappable_position_side_snapshot_preserves_stage_10e_fail_closed_outcome() -> None:
    final_result = _actionable_final_recommendation_result()
    results = construct_tracked_recommendations(
        final_recommendation_construction_result=final_result,
        as_of=NOW,
        market=MarketType.FX,
        pre_existing_positions_read_status="UNMAPPABLE_POSITION_SIDE",
        pre_existing_positions=(),
    )
    assert results[0].tracking_creation_result.outcome is MT5TrackedRecommendationCreationOutcome.SNAPSHOT_UNAVAILABLE


# --- I: zero actionable recommendations ---


def test_zero_actionable_recommendations_yields_empty_tuple() -> None:
    pipeline_result = run_pipeline(technical=None, m15_market_structure=None)
    final_result = construct_final_recommendations(
        decision_risk_pipeline_result=pipeline_result,
        symbol_facts=symbol_facts(),
        account_currency="USD",
        trade_ids={},
        as_of=NOW,
    )
    results = construct_tracked_recommendations(
        final_recommendation_construction_result=final_result,
        as_of=NOW,
        market=MarketType.FX,
        pre_existing_positions_read_status="OK",
        pre_existing_positions=(),
    )
    assert results == ()


# --- J: one actionable recommendation ---


def test_one_actionable_recommendation_yields_one_result() -> None:
    final_result = _actionable_final_recommendation_result()
    results = construct_tracked_recommendations(
        final_recommendation_construction_result=final_result,
        as_of=NOW,
        market=MarketType.FX,
        pre_existing_positions_read_status="OK",
        pre_existing_positions=(),
    )
    assert len(results) == 1


# --- K/L: multiple + opposite-direction recommendations tracked independently ---


def test_multiple_opposite_direction_recommendations_tracked_independently() -> None:
    final_result = _opposite_direction_final_recommendation_result()
    results = construct_tracked_recommendations(
        final_recommendation_construction_result=final_result,
        as_of=NOW,
        market=MarketType.FX,
        pre_existing_positions_read_status="OK",
        pre_existing_positions=(),
    )
    assert len(results) == 2
    trade_ids = {r.trade_id for r in results}
    assert trade_ids == {"trade-long", "trade-short"}

    long_result = next(r for r in results if r.trade_id == "trade-long")
    short_result = next(r for r in results if r.trade_id == "trade-short")
    long_tracked = long_result.tracking_creation_result.tracked_recommendation
    short_tracked = short_result.tracking_creation_result.tracked_recommendation
    assert long_tracked.position_record.direction is TradeDirection.LONG
    assert short_tracked.position_record.direction is TradeDirection.SHORT
    assert long_result.provenance.family is StrategyFamily.TREND_FOLLOWING
    assert short_result.provenance.family is StrategyFamily.BREAKOUT


# --- M: deterministic family order ---


def test_results_preserve_deterministic_family_order() -> None:
    final_result = _opposite_direction_final_recommendation_result()
    expected_family_order = tuple(
        r.family for r in final_result.family_results if r.verdict is FinalRecommendationVerdict.ACTIONABLE
    )
    results = construct_tracked_recommendations(
        final_recommendation_construction_result=final_result,
        as_of=NOW,
        market=MarketType.FX,
        pre_existing_positions_read_status="OK",
        pre_existing_positions=(),
    )
    actual_family_order = tuple(r.provenance.family for r in results)
    assert actual_family_order == expected_family_order


# --- N: provenance exact mapping ---


def test_provenance_exact_field_mapping() -> None:
    final_result = _actionable_final_recommendation_result()
    recommendation = next(
        r.recommendation for r in final_result.family_results if r.family is StrategyFamily.TREND_FOLLOWING
    )
    results = construct_tracked_recommendations(
        final_recommendation_construction_result=final_result,
        as_of=NOW,
        market=MarketType.FX,
        pre_existing_positions_read_status="OK",
        pre_existing_positions=(),
    )
    provenance = results[0].provenance
    assert provenance.trade_id == recommendation.trade_id
    assert provenance.family == recommendation.family
    assert provenance.approved_risk_amount == recommendation.approved_risk_amount
    assert provenance.account_currency == recommendation.account_currency


# --- determinism ---


def test_determinism_same_inputs_produce_equal_outputs() -> None:
    final_result = _actionable_final_recommendation_result()
    kwargs = dict(
        final_recommendation_construction_result=final_result,
        as_of=NOW,
        market=MarketType.FX,
        pre_existing_positions_read_status="OK",
        pre_existing_positions=(),
    )
    first = construct_tracked_recommendations(**kwargs)
    second = construct_tracked_recommendations(**kwargs)
    assert first == second
