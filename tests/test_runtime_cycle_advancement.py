"""Part F existing-tracking advancement sequencing - pure unit tests (Final
Runtime Integration, Part F).

Tests ``app.orchestration.runtime_cycle._advance_all_existing_tracking`` and
``_compute_history_start`` directly - deterministic sequencing over the
existing, unmodified ``advance_tracked_recommendation`` only; no custom
matching/PnL logic lives here.
"""

from __future__ import annotations

from datetime import timedelta

import app.orchestration.runtime_cycle as runtime_cycle_module
from app.core.enums.mt5_matching import MT5MatchOutcome
from app.core.enums.trade import TradeStatus
from app.orchestration.runtime_cycle import _advance_all_existing_tracking, _compute_history_start
from tests.mt5_matching_support import SIGNAL_TIME, VALID_UNTIL, default_candidate_deal, default_position_record, default_tracked_recommendation


# --- _compute_history_start ---


def test_history_start_is_trading_day_start_when_no_tracked_recommendations() -> None:
    result = _compute_history_start(trading_day_start=SIGNAL_TIME, tracked_by_trade_id={})
    assert result == SIGNAL_TIME


def test_history_start_uses_earliest_signal_time_when_earlier_than_trading_day() -> None:
    earlier_signal_time = SIGNAL_TIME - timedelta(days=2)
    tracked = {
        "t1": default_tracked_recommendation(position_record=default_position_record(trade_id="t1", signal_time=earlier_signal_time, valid_until=earlier_signal_time + timedelta(minutes=5)))
    }
    result = _compute_history_start(trading_day_start=SIGNAL_TIME, tracked_by_trade_id=tracked)
    assert result == earlier_signal_time


def test_history_start_uses_trading_day_start_when_all_signal_times_are_later() -> None:
    later_signal_time = SIGNAL_TIME + timedelta(hours=1)
    tracked = {
        "t1": default_tracked_recommendation(position_record=default_position_record(trade_id="t1", signal_time=later_signal_time, valid_until=later_signal_time + timedelta(minutes=5)))
    }
    result = _compute_history_start(trading_day_start=SIGNAL_TIME, tracked_by_trade_id=tracked)
    assert result == SIGNAL_TIME


# --- _advance_all_existing_tracking: uses only the existing pure function ---


def test_advances_single_recommendation_to_matched() -> None:
    tracked = default_tracked_recommendation(position_record=default_position_record(trade_id="t1"))
    results = _advance_all_existing_tracking(
        as_of=SIGNAL_TIME + timedelta(minutes=1),
        tracked_by_trade_id={"t1": tracked},
        deals=(default_candidate_deal(),),
        history_read_status="OK",
        history_covers_until=SIGNAL_TIME + timedelta(minutes=1),
    )
    results_by_id = dict(results)
    assert results_by_id["t1"].matched_position_id == 7001
    assert results_by_id["t1"].position_record.status is TradeStatus.OPEN


def test_no_op_when_history_unavailable() -> None:
    tracked = default_tracked_recommendation(position_record=default_position_record(trade_id="t1"))
    results = _advance_all_existing_tracking(
        as_of=SIGNAL_TIME + timedelta(minutes=1),
        tracked_by_trade_id={"t1": tracked},
        deals=(),
        history_read_status="UNAVAILABLE",
        history_covers_until=SIGNAL_TIME + timedelta(minutes=1),
    )
    results_by_id = dict(results)
    assert results_by_id["t1"].matched_position_id is None
    assert results_by_id["t1"].position_record.status is TradeStatus.PENDING


def test_newly_matched_position_immediately_reserved_for_later_recommendation_in_same_pass() -> None:
    """Two unmatched recommendations (lexicographic order t1 < t2) both
    structurally eligible for the SAME single candidate position_id: only
    the first processed may claim it; the second must see it excluded via
    ``already_claimed_position_ids`` within the SAME pass - never both
    independently matching the same broker position."""
    tracked_1 = default_tracked_recommendation(position_record=default_position_record(trade_id="t1"))
    tracked_2 = default_tracked_recommendation(position_record=default_position_record(trade_id="t2"))
    results = _advance_all_existing_tracking(
        as_of=SIGNAL_TIME + timedelta(minutes=1),
        tracked_by_trade_id={"t2": tracked_2, "t1": tracked_1},
        deals=(default_candidate_deal(),),
        history_read_status="OK",
        history_covers_until=SIGNAL_TIME + timedelta(minutes=1),
    )
    results_by_id = dict(results)
    assert results_by_id["t1"].matched_position_id == 7001
    assert results_by_id["t1"].last_match_outcome is MT5MatchOutcome.MATCHED
    assert results_by_id["t2"].matched_position_id is None
    assert results_by_id["t2"].last_match_outcome is MT5MatchOutcome.NO_CANDIDATE_YET


def test_seeds_claimed_set_from_already_matched_recommendations() -> None:
    """A recommendation already matched to position_id 7001 in a previous
    cycle must keep position_id 7001 reserved against any OTHER
    recommendation this cycle, even though 7001's own claimant never
    re-matches (its matched_position_id is immutable)."""
    already_matched = default_tracked_recommendation(
        position_record=default_position_record(trade_id="t1", status=TradeStatus.OPEN),
        matched_position_id=7001,
        last_match_outcome=MT5MatchOutcome.MATCHED,
    )
    other_unmatched = default_tracked_recommendation(position_record=default_position_record(trade_id="t2"))
    captured: dict[str, tuple[int, ...]] = {}

    def _fake_advance(*, as_of, tracked, deals, history_read_status, history_covers_until, already_claimed_position_ids):
        captured[tracked.position_record.trade_id] = already_claimed_position_ids
        return tracked

    original = runtime_cycle_module.advance_tracked_recommendation
    runtime_cycle_module.advance_tracked_recommendation = _fake_advance
    try:
        _advance_all_existing_tracking(
            as_of=SIGNAL_TIME + timedelta(minutes=1),
            tracked_by_trade_id={"t1": already_matched, "t2": other_unmatched},
            deals=(),
            history_read_status="OK",
            history_covers_until=SIGNAL_TIME + timedelta(minutes=1),
        )
    finally:
        runtime_cycle_module.advance_tracked_recommendation = original

    assert captured["t1"] == ()  # own matched id excluded from its own claimed set
    assert captured["t2"] == (7001,)  # sees t1's existing claim


def test_processing_order_is_lexicographic_trade_id() -> None:
    order: list[str] = []

    def _fake_advance(*, as_of, tracked, deals, history_read_status, history_covers_until, already_claimed_position_ids):
        order.append(tracked.position_record.trade_id)
        return tracked

    original = runtime_cycle_module.advance_tracked_recommendation
    runtime_cycle_module.advance_tracked_recommendation = _fake_advance
    try:
        _advance_all_existing_tracking(
            as_of=SIGNAL_TIME,
            tracked_by_trade_id={
                "trade-c": default_tracked_recommendation(position_record=default_position_record(trade_id="trade-c")),
                "trade-a": default_tracked_recommendation(position_record=default_position_record(trade_id="trade-a")),
                "trade-b": default_tracked_recommendation(position_record=default_position_record(trade_id="trade-b")),
            },
            deals=(),
            history_read_status="OK",
            history_covers_until=SIGNAL_TIME,
        )
    finally:
        runtime_cycle_module.advance_tracked_recommendation = original

    assert order == ["trade-a", "trade-b", "trade-c"]


def test_ambiguous_match_preserved_unchanged() -> None:
    tracked = default_tracked_recommendation(position_record=default_position_record(trade_id="t1"))
    deal_a = default_candidate_deal(ticket=1, position_id=9001)
    deal_b = default_candidate_deal(ticket=2, position_id=9002)
    results = _advance_all_existing_tracking(
        as_of=SIGNAL_TIME + timedelta(minutes=1),
        tracked_by_trade_id={"t1": tracked},
        deals=(deal_a, deal_b),
        history_read_status="OK",
        history_covers_until=SIGNAL_TIME + timedelta(minutes=1),
    )
    results_by_id = dict(results)
    assert results_by_id["t1"].last_match_outcome is MT5MatchOutcome.AMBIGUOUS
    assert results_by_id["t1"].matched_position_id is None


def test_expired_confirmed_unfilled_preserved() -> None:
    tracked = default_tracked_recommendation(position_record=default_position_record(trade_id="t1"))
    results = _advance_all_existing_tracking(
        as_of=VALID_UNTIL + timedelta(minutes=1),
        tracked_by_trade_id={"t1": tracked},
        deals=(),
        history_read_status="OK",
        history_covers_until=VALID_UNTIL + timedelta(minutes=1),
    )
    results_by_id = dict(results)
    assert results_by_id["t1"].last_match_outcome is MT5MatchOutcome.EXPIRED_CONFIRMED_UNFILLED
    assert results_by_id["t1"].position_record.status is TradeStatus.NOT_FILLED
