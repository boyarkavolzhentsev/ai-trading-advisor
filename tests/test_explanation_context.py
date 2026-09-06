"""LLM Explanation Layer - deterministic context/authoritative-card tests
(NEXT STAGE, Core)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from app.orchestration.explanation import build_explanation_context, build_recommendation_cards, build_tracking_cards
from tests.explanation_support import (
    ready_actionable_hedging_result,
    ready_actionable_hedging_result_with_currency,
    ready_multiple_actionable_hedging_result,
)


# --- A: deterministic context stability ---


def test_context_is_stable_across_repeated_builds(tmp_path: Path) -> None:
    result = ready_actionable_hedging_result(tmp_path / "a")
    first = build_explanation_context(result)
    second = build_explanation_context(result)
    assert first == second


def test_recommendation_cards_stable_across_repeated_builds(tmp_path: Path) -> None:
    result = ready_actionable_hedging_result(tmp_path / "a")
    assert build_recommendation_cards(result) == build_recommendation_cards(result)


# --- B: authoritative card values exactly equal source FinalRecommendation ---


def test_recommendation_card_values_exactly_equal_source_recommendation(tmp_path: Path) -> None:
    result = ready_actionable_hedging_result(tmp_path)
    final = result.final_recommendation_construction_result
    recommendation = next(r.recommendation for r in final.family_results if r.recommendation is not None)

    cards = build_recommendation_cards(result)
    assert len(cards) == 1
    card = cards[0]

    assert card.trade_id == recommendation.trade_id
    assert card.family == recommendation.family
    assert card.symbol == recommendation.symbol
    assert card.direction == recommendation.direction
    assert card.entry_price == recommendation.entry_price
    assert card.stop_loss == recommendation.stop_loss
    assert card.take_profit_levels == recommendation.take_profit_levels
    assert card.approved_volume == recommendation.approved_volume
    assert card.approved_risk_amount == recommendation.approved_risk_amount
    assert card.account_currency == recommendation.account_currency

    persistence = result.new_tracking_persistence_outcomes[0]
    assert card.tracking_creation_outcome == persistence.tracking_creation_outcome
    assert card.tracking_persisted == persistence.tracking_persisted
    assert card.provenance_persisted == persistence.provenance_persisted


def test_no_card_for_blocked_family(tmp_path: Path) -> None:
    from tests.explanation_support import ready_no_actionable_result

    result = ready_no_actionable_result(tmp_path)
    assert build_recommendation_cards(result) == ()


# --- C: account currency copied unchanged ---


@pytest.mark.parametrize("currency", ["USD", "EUR", "DKK", "XAG"])
def test_account_currency_copied_unchanged(tmp_path: Path, currency: str) -> None:
    result = ready_actionable_hedging_result_with_currency(tmp_path, currency)
    cards = build_recommendation_cards(result)
    assert cards[0].account_currency == currency

    context = build_explanation_context(result)
    currency_fact = next(f for f in context.facts if f.fact_id == "runtime.account_currency")
    assert currency_fact.value == currency


# --- E: LLM context contains only strings, never authoritative Decimal/enum objects ---


def test_context_facts_are_string_only(tmp_path: Path) -> None:
    result = ready_actionable_hedging_result(tmp_path)
    context = build_explanation_context(result)

    for fact in context.facts:
        assert isinstance(fact.value, str)
    for fact in context.warnings:
        assert isinstance(fact.value, str)
    for group in context.recommendation_facts:
        for fact in group:
            assert isinstance(fact.value, str)
            assert not isinstance(fact.value, Decimal)
    for group in context.tracking_facts:
        for fact in group:
            assert isinstance(fact.value, str)


def test_context_recommendation_facts_never_embed_card_object(tmp_path: Path) -> None:
    result = ready_actionable_hedging_result(tmp_path)
    context = build_explanation_context(result)
    # every leaf in recommendation_facts is a GroundedFact (fact_id/label/value:str),
    # never a RecommendationFactCard - enforced structurally by the model shape itself:
    for group in context.recommendation_facts:
        for fact in group:
            assert hasattr(fact, "fact_id")
            assert hasattr(fact, "value")
            assert not hasattr(fact, "entry_price")  # never the authoritative card


# --- G/H: multiple recommendation preservation, order, no ranking ---


def test_multiple_recommendations_all_survive(tmp_path: Path) -> None:
    result = ready_multiple_actionable_hedging_result(tmp_path)
    cards = build_recommendation_cards(result)
    assert len(cards) == 2


def test_recommendation_card_order_matches_family_results_order(tmp_path: Path) -> None:
    result = ready_multiple_actionable_hedging_result(tmp_path)
    final = result.final_recommendation_construction_result
    expected_order = tuple(r.family for r in final.family_results if r.recommendation is not None)

    cards = build_recommendation_cards(result)
    assert tuple(card.family for card in cards) == expected_order

    context = build_explanation_context(result)
    assert len(context.recommendation_facts) == len(cards)


def test_no_ranking_no_winner_selection_both_recommendations_independent(tmp_path: Path) -> None:
    result = ready_multiple_actionable_hedging_result(tmp_path)
    cards = build_recommendation_cards(result)
    trade_ids = {card.trade_id for card in cards}
    assert trade_ids == {"trade-long", "trade-short"}
    directions = {card.trade_id: card.direction for card in cards}
    assert directions["trade-long"] != directions["trade-short"]


# --- tracking cards ---


def test_tracking_card_built_from_existing_advancement(tmp_path: Path) -> None:
    from tests.explanation_support import tracking_lifecycle_result

    result = tracking_lifecycle_result(tmp_path, "OPEN")
    cards = build_tracking_cards(result)
    assert len(cards) == 1
    assert cards[0].trade_id == "t1"
    assert cards[0].status.value == "OPEN"
    assert cards[0].matched_position_id == 7001
    # I: advanced tracking + account_facts available -> current-cycle broker
    # account currency, a direct unconverted copy (never Part E provenance,
    # which is not read during normal advancement, and never fabricated):
    assert result.account_facts is not None
    assert cards[0].account_currency == result.account_facts.currency


def test_advanced_tracking_currency_matches_account_facts_for_arbitrary_currency(tmp_path: Path) -> None:
    """I (parametrized differently): the mapping is a direct copy, not a
    coincidence of any particular default - proven by overriding the account
    currency to a non-default value and observing an EXISTING (advanced)
    tracking card track it exactly."""
    from tests.explanation_support import make_stores
    from tests.mt5_matching_support import default_candidate_deal, default_position_record, default_tracked_recommendation
    from tests.runtime_cycle_support import RuntimeCycleFakeClient, default_account_facts

    stores = make_stores(tmp_path)
    _, tracking_persistence, _ = stores
    tracking_persistence.write("t1", default_tracked_recommendation(position_record=default_position_record(trade_id="t1")))

    from app.core.config.mt5_rollover import MT5RolloverPolicyConfig
    from app.core.enums.market import MarketType
    from app.orchestration.runtime_cycle import run_runtime_cycle
    from tests.final_recommendation_support import NOW, context as _context, symbol_facts
    from tests.risk_gate_support import default_config

    client = RuntimeCycleFakeClient(
        account_facts=default_account_facts(currency="DKK"),
        positions_result=("OK", ()),
        symbol_facts_by_symbol={"BTCUSDT": symbol_facts()},
        history_deals_result=("OK", (default_candidate_deal(),)),
    )
    result = run_runtime_cycle(
        client=client,
        as_of=NOW,
        rollover_policy=MT5RolloverPolicyConfig(rollover_timezone="UTC", rollover_hour=0),
        rollover_persistence=stores[0],
        tracking_persistence=stores[1],
        provenance_persistence=stores[2],
        trading_cycle_config=default_config(),
        market=MarketType.CRYPTO,
        trade_ids={},
        context=_context(),
    )

    cards = build_tracking_cards(result)
    assert len(cards) == 1
    assert cards[0].account_currency == "DKK"


def test_advanced_tracking_currency_none_when_account_facts_unavailable_pnl_present(tmp_path: Path) -> None:
    """J: the legitimate reachable degraded case - account_facts unavailable
    this cycle, but a terminal PnL is still genuinely known (existing-tracking
    advancement is independent of account_facts). account_currency must
    remain None (never inferred, never hardcoded, never borrowed from another
    trade) while the authoritative pnl value itself is never suppressed."""
    from datetime import timedelta
    from decimal import Decimal

    from app.core.enums.mt5_history import MT5DealEntry
    from app.core.enums.mt5_runtime import MT5ConnectivityState
    from app.core.models.mt5_runtime import MT5RuntimeStatus
    from tests.explanation_support import make_stores
    from tests.final_recommendation_support import NOW
    from tests.mt5_matching_support import SIGNAL_TIME, default_candidate_deal, default_position_record, default_tracked_recommendation
    from tests.runtime_cycle_support import RuntimeCycleFakeClient
    from app.orchestration.runtime_cycle import run_runtime_cycle
    from app.core.config.mt5_rollover import MT5RolloverPolicyConfig
    from app.core.enums.market import MarketType
    from tests.risk_gate_support import default_config
    from tests.final_recommendation_support import context as _context

    stores = make_stores(tmp_path)
    _, tracking_persistence, _ = stores
    tracking_persistence.write("t1", default_tracked_recommendation(position_record=default_position_record(trade_id="t1")))

    entry = default_candidate_deal(ticket=1, commission=Decimal("0"))
    exit_deal = default_candidate_deal(
        ticket=2, entry=MT5DealEntry.OUT, time=SIGNAL_TIME + timedelta(minutes=3), profit=Decimal("50"), commission=Decimal("0")
    )
    client = RuntimeCycleFakeClient(
        runtime_status=MT5RuntimeStatus(as_of=NOW, state=MT5ConnectivityState.AVAILABLE),
        account_facts=None,  # legitimate race: connectivity AVAILABLE but account_facts itself unavailable
        positions_result=("UNAVAILABLE", ()),
        history_deals_result=("OK", (entry, exit_deal)),
    )
    result = run_runtime_cycle(
        client=client,
        as_of=SIGNAL_TIME + timedelta(minutes=4),
        rollover_policy=MT5RolloverPolicyConfig(rollover_timezone="UTC", rollover_hour=0),
        rollover_persistence=stores[0],
        tracking_persistence=stores[1],
        provenance_persistence=stores[2],
        trading_cycle_config=default_config(),
        market=MarketType.CRYPTO,
        trade_ids={},
        context=_context(),
    )

    assert result.account_facts is None
    assert len(result.advanced_tracking) == 1
    assert result.advanced_tracking[0].tracked_recommendation.position_record.pnl == Decimal("50")

    cards = build_tracking_cards(result)
    assert len(cards) == 1
    assert cards[0].pnl == Decimal("50")  # authoritative PnL never suppressed
    assert cards[0].account_currency is None  # never inferred, never hardcoded, never borrowed
