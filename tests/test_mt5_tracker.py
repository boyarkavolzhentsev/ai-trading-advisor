"""Stage 10E pure ``reconstruct_position_lifecycle``, ``create_tracked_
recommendation``, ``advance_tracked_recommendation``: snapshot safety, entry
aggregation, partial/full close, WIN/LOSS/BREAKEVEN, match immutability,
expiry, MT5-unavailable, OUT_BY/UNKNOWN fail-closed, manual-trade
separation."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from app.core.enums.market import MarketType
from app.core.enums.mt5_history import MT5DealEntry, MT5DealType, MT5RealizedPnLBlockReason, MT5RealizedPnLOutcome
from app.core.enums.mt5_matching import MT5MatchOutcome, MT5TrackedRecommendationCreationOutcome
from app.core.enums.trade import TradeDirection, TradeStatus
from app.mt5.tracker import advance_tracked_recommendation, create_tracked_recommendation, reconstruct_position_lifecycle
from tests.mt5_matching_support import SIGNAL_TIME, VALID_UNTIL, default_candidate_deal, default_tracked_recommendation
from tests.mt5_position_support import default_position

# --- create_tracked_recommendation: snapshot safety ---


def _create(**overrides):
    fields = dict(
        as_of=SIGNAL_TIME,
        trade_id="trade-1",
        symbol="EURUSD",
        market=MarketType.FX,
        direction=TradeDirection.LONG,
        signal_time=SIGNAL_TIME,
        valid_until=VALID_UNTIL,
        planned_entry=Decimal("100"),
        stop_loss=Decimal("95"),
        approved_broker_volume=Decimal("1"),
        pre_existing_positions_read_status="OK",
        pre_existing_positions=(),
    )
    fields.update(overrides)
    return create_tracked_recommendation(**fields)


def test_confirmed_ok_empty_snapshot_creates_valid_tracking_state() -> None:
    result = _create()
    assert result.outcome is MT5TrackedRecommendationCreationOutcome.CREATED
    assert result.tracked_recommendation.pre_existing_position_ids == ()


def test_confirmed_ok_populated_snapshot_preserved() -> None:
    result = _create(pre_existing_positions=(default_position(ticket=42, symbol="EURUSD"),))
    assert result.outcome is MT5TrackedRecommendationCreationOutcome.CREATED
    assert result.tracked_recommendation.pre_existing_position_ids == (42,)


def test_populated_snapshot_filters_to_recommendation_symbol() -> None:
    result = _create(
        pre_existing_positions=(
            default_position(ticket=42, symbol="EURUSD"),
            default_position(ticket=99, symbol="XAUUSD"),
        )
    )
    assert result.tracked_recommendation.pre_existing_position_ids == (42,)


def test_unavailable_snapshot_is_not_converted_to_empty() -> None:
    result = _create(pre_existing_positions_read_status="UNAVAILABLE")
    assert result.outcome is MT5TrackedRecommendationCreationOutcome.SNAPSHOT_UNAVAILABLE
    assert result.tracked_recommendation is None


def test_unmappable_position_side_is_not_converted_to_empty() -> None:
    result = _create(pre_existing_positions_read_status="UNMAPPABLE_POSITION_SIDE")
    assert result.outcome is MT5TrackedRecommendationCreationOutcome.SNAPSHOT_UNAVAILABLE
    assert result.tracked_recommendation is None


def test_unsafe_snapshot_never_creates_a_normal_matchable_tracking_state() -> None:
    unavailable = _create(pre_existing_positions_read_status="UNAVAILABLE")
    unmappable = _create(pre_existing_positions_read_status="UNMAPPABLE_POSITION_SIDE")
    assert unavailable.tracked_recommendation is None
    assert unmappable.tracked_recommendation is None


def test_created_tracking_state_starts_pending_unmatched() -> None:
    result = _create()
    tracked = result.tracked_recommendation
    assert tracked.matched_position_id is None
    assert tracked.position_record.status is TradeStatus.PENDING


# --- reconstruct_position_lifecycle ---


def test_lifecycle_single_fill_still_open() -> None:
    deals = (default_candidate_deal(),)
    assessment = reconstruct_position_lifecycle(position_id=7001, deals=deals, as_of=SIGNAL_TIME + timedelta(minutes=1))
    assert assessment.outcome is MT5RealizedPnLOutcome.READY
    assert assessment.is_fully_closed is False
    assert assessment.actual_entry == Decimal("100")
    assert assessment.actual_entry_time == SIGNAL_TIME + timedelta(minutes=1)


def test_lifecycle_volume_weighted_actual_entry_multiple_fills() -> None:
    first = default_candidate_deal(ticket=1, time=SIGNAL_TIME + timedelta(minutes=1), price=Decimal("100"), volume=Decimal("1"))
    second = default_candidate_deal(ticket=2, time=SIGNAL_TIME + timedelta(minutes=2), price=Decimal("104"), volume=Decimal("1"))
    assessment = reconstruct_position_lifecycle(position_id=7001, deals=(first, second), as_of=SIGNAL_TIME + timedelta(minutes=3))
    assert assessment.actual_entry == Decimal("102")
    assert assessment.actual_entry_time == SIGNAL_TIME + timedelta(minutes=1)


def test_lifecycle_earliest_fill_time_used_regardless_of_input_order() -> None:
    first = default_candidate_deal(ticket=1, time=SIGNAL_TIME + timedelta(minutes=2))
    second = default_candidate_deal(ticket=2, time=SIGNAL_TIME + timedelta(minutes=1))
    assessment = reconstruct_position_lifecycle(position_id=7001, deals=(first, second), as_of=SIGNAL_TIME)
    assert assessment.actual_entry_time == SIGNAL_TIME + timedelta(minutes=1)


def test_lifecycle_partial_close_remains_open() -> None:
    entry = default_candidate_deal(ticket=1, volume=Decimal("2"))
    partial_exit = default_candidate_deal(
        ticket=2, entry=MT5DealEntry.OUT, volume=Decimal("1"), time=SIGNAL_TIME + timedelta(minutes=2), profit=Decimal("10")
    )
    assessment = reconstruct_position_lifecycle(position_id=7001, deals=(entry, partial_exit), as_of=SIGNAL_TIME)
    assert assessment.is_fully_closed is False
    assert assessment.exit_price is None
    assert assessment.exit_time is None


def test_lifecycle_multiple_partial_closes_then_full_close() -> None:
    entry = default_candidate_deal(ticket=1, volume=Decimal("3"))
    exit1 = default_candidate_deal(ticket=2, entry=MT5DealEntry.OUT, volume=Decimal("1"), time=SIGNAL_TIME + timedelta(minutes=2), profit=Decimal("5"))
    exit2 = default_candidate_deal(ticket=3, entry=MT5DealEntry.OUT, volume=Decimal("2"), time=SIGNAL_TIME + timedelta(minutes=3), profit=Decimal("10"))
    assessment = reconstruct_position_lifecycle(position_id=7001, deals=(entry, exit1, exit2), as_of=SIGNAL_TIME)
    assert assessment.is_fully_closed is True
    assert assessment.exit_time == SIGNAL_TIME + timedelta(minutes=3)


def test_lifecycle_full_close_volume_weighted_exit_price() -> None:
    entry = default_candidate_deal(ticket=1, volume=Decimal("2"))
    exit1 = default_candidate_deal(ticket=2, entry=MT5DealEntry.OUT, volume=Decimal("1"), price=Decimal("100"), time=SIGNAL_TIME + timedelta(minutes=2), profit=Decimal("0"))
    exit2 = default_candidate_deal(ticket=3, entry=MT5DealEntry.OUT, volume=Decimal("1"), price=Decimal("110"), time=SIGNAL_TIME + timedelta(minutes=3), profit=Decimal("10"))
    assessment = reconstruct_position_lifecycle(position_id=7001, deals=(entry, exit1, exit2), as_of=SIGNAL_TIME)
    assert assessment.exit_price == Decimal("105")


def test_lifecycle_win() -> None:
    entry = default_candidate_deal(ticket=1, commission=Decimal("-2"))
    exit_deal = default_candidate_deal(ticket=2, entry=MT5DealEntry.OUT, time=SIGNAL_TIME + timedelta(minutes=2), profit=Decimal("50"), commission=Decimal("-2"))
    assessment = reconstruct_position_lifecycle(position_id=7001, deals=(entry, exit_deal), as_of=SIGNAL_TIME)
    assert assessment.realized_pnl == Decimal("46")


def test_lifecycle_loss() -> None:
    entry = default_candidate_deal(ticket=1, commission=Decimal("-2"))
    exit_deal = default_candidate_deal(ticket=2, entry=MT5DealEntry.OUT, time=SIGNAL_TIME + timedelta(minutes=2), profit=Decimal("-50"), commission=Decimal("-2"))
    assessment = reconstruct_position_lifecycle(position_id=7001, deals=(entry, exit_deal), as_of=SIGNAL_TIME)
    assert assessment.realized_pnl == Decimal("-54")


def test_lifecycle_breakeven() -> None:
    entry = default_candidate_deal(ticket=1, commission=Decimal("0"))
    exit_deal = default_candidate_deal(ticket=2, entry=MT5DealEntry.OUT, time=SIGNAL_TIME + timedelta(minutes=2), profit=Decimal("0"), commission=Decimal("0"))
    assessment = reconstruct_position_lifecycle(position_id=7001, deals=(entry, exit_deal), as_of=SIGNAL_TIME)
    assert assessment.realized_pnl == Decimal("0")


def test_lifecycle_entry_commission_counted_once() -> None:
    entry = default_candidate_deal(ticket=1, commission=Decimal("-3"), fee=Decimal("-1"), profit=Decimal("999"), swap=Decimal("999"))
    assessment = reconstruct_position_lifecycle(position_id=7001, deals=(entry,), as_of=SIGNAL_TIME)
    assert assessment.realized_pnl == Decimal("-4")


def test_lifecycle_exit_commission_swap_fee_included() -> None:
    entry = default_candidate_deal(ticket=1, commission=Decimal("0"))
    exit_deal = default_candidate_deal(
        ticket=2, entry=MT5DealEntry.OUT, time=SIGNAL_TIME + timedelta(minutes=2), profit=Decimal("20"), commission=Decimal("-1"), swap=Decimal("-0.5"), fee=Decimal("-0.25")
    )
    assessment = reconstruct_position_lifecycle(position_id=7001, deals=(entry, exit_deal), as_of=SIGNAL_TIME)
    assert assessment.realized_pnl == Decimal("18.25")


def test_lifecycle_out_by_fails_closed() -> None:
    entry = default_candidate_deal(ticket=1)
    out_by = default_candidate_deal(ticket=2, entry=MT5DealEntry.OUT_BY, time=SIGNAL_TIME + timedelta(minutes=2))
    assessment = reconstruct_position_lifecycle(position_id=7001, deals=(entry, out_by), as_of=SIGNAL_TIME)
    assert assessment.outcome is MT5RealizedPnLOutcome.BLOCKED
    assert assessment.blocked_reasons == (MT5RealizedPnLBlockReason.UNSUPPORTED_OUT_BY,)
    assert assessment.realized_pnl is None


def test_lifecycle_unknown_deal_type_fails_closed() -> None:
    entry = default_candidate_deal(ticket=1)
    unknown = default_candidate_deal(ticket=2, deal_type=MT5DealType.UNKNOWN, time=SIGNAL_TIME + timedelta(minutes=2))
    assessment = reconstruct_position_lifecycle(position_id=7001, deals=(entry, unknown), as_of=SIGNAL_TIME)
    assert assessment.outcome is MT5RealizedPnLOutcome.BLOCKED
    assert assessment.blocked_reasons == (MT5RealizedPnLBlockReason.UNMAPPABLE_DEAL_TYPE,)


def test_lifecycle_no_partial_pnl_when_blocked() -> None:
    entry = default_candidate_deal(ticket=1, profit=Decimal("500"))
    out_by = default_candidate_deal(ticket=2, entry=MT5DealEntry.OUT_BY, time=SIGNAL_TIME + timedelta(minutes=2), profit=Decimal("500"))
    assessment = reconstruct_position_lifecycle(position_id=7001, deals=(entry, out_by), as_of=SIGNAL_TIME)
    assert assessment.realized_pnl is None
    assert assessment.is_fully_closed is None


def test_lifecycle_filters_by_position_id() -> None:
    """A deal belonging to an unrelated position_id must never contribute."""
    entry = default_candidate_deal(ticket=1, position_id=7001)
    unrelated = default_candidate_deal(ticket=2, position_id=9999, profit=Decimal("9999"))
    assessment = reconstruct_position_lifecycle(position_id=7001, deals=(entry, unrelated), as_of=SIGNAL_TIME)
    assert assessment.realized_pnl == entry.commission + entry.fee


# --- advance_tracked_recommendation: matching + immutability ---


def _advance(tracked, deals, **overrides):
    fields = dict(
        as_of=SIGNAL_TIME + timedelta(minutes=1),
        deals=deals,
        history_read_status="OK",
        history_covers_until=SIGNAL_TIME + timedelta(minutes=1),
        already_claimed_position_ids=(),
    )
    fields.update(overrides)
    return advance_tracked_recommendation(tracked=tracked, **fields)


def test_advance_matches_and_opens_in_one_cycle() -> None:
    tracked = default_tracked_recommendation()
    updated = _advance(tracked, (default_candidate_deal(),))
    assert updated.matched_position_id == 7001
    assert updated.position_record.status is TradeStatus.OPEN
    assert updated.last_match_outcome is MT5MatchOutcome.MATCHED


def test_advance_matches_and_closes_in_one_cycle_if_already_fully_closed() -> None:
    tracked = default_tracked_recommendation()
    entry = default_candidate_deal(ticket=1)
    exit_deal = default_candidate_deal(ticket=2, entry=MT5DealEntry.OUT, time=SIGNAL_TIME + timedelta(minutes=2), profit=Decimal("50"))
    updated = _advance(tracked, (entry, exit_deal), as_of=SIGNAL_TIME + timedelta(minutes=3), history_covers_until=SIGNAL_TIME + timedelta(minutes=3))
    assert updated.position_record.status is TradeStatus.WIN


def test_advance_zero_candidates_before_expiry_leaves_position_record_untouched() -> None:
    tracked = default_tracked_recommendation()
    updated = _advance(tracked, ())
    assert updated.matched_position_id is None
    assert updated.position_record.status is TradeStatus.PENDING
    assert updated.last_match_outcome is MT5MatchOutcome.NO_CANDIDATE_YET


def test_advance_confirmed_unfilled_at_expiry() -> None:
    tracked = default_tracked_recommendation()
    updated = _advance(tracked, (), as_of=VALID_UNTIL + timedelta(minutes=1), history_covers_until=VALID_UNTIL)
    assert updated.position_record.status is TradeStatus.NOT_FILLED
    assert updated.last_match_outcome is MT5MatchOutcome.EXPIRED_CONFIRMED_UNFILLED


def test_advance_read_unavailable_never_becomes_not_filled() -> None:
    tracked = default_tracked_recommendation()
    updated = _advance(tracked, (), as_of=VALID_UNTIL + timedelta(days=1), history_read_status="UNAVAILABLE")
    assert updated.position_record.status is TradeStatus.PENDING
    assert updated.last_match_outcome is MT5MatchOutcome.READ_UNAVAILABLE


def test_advance_partial_fill_never_becomes_not_filled_and_stays_unmatched() -> None:
    """A genuine partial fill (multi-fill correctness patch) must never be
    mistaken for a confirmed-unfilled recommendation, even well past
    expiry."""
    tracked = default_tracked_recommendation(approved_broker_volume=Decimal("0.10"))
    partial = default_candidate_deal(volume=Decimal("0.04"))
    updated = _advance(tracked, (partial,), as_of=VALID_UNTIL + timedelta(days=1), history_covers_until=VALID_UNTIL)
    assert updated.matched_position_id is None
    assert updated.position_record.status is TradeStatus.PENDING
    assert updated.last_match_outcome is MT5MatchOutcome.PARTIAL_FILL


def test_advance_volume_mismatch_never_becomes_not_filled_or_matched() -> None:
    tracked = default_tracked_recommendation(approved_broker_volume=Decimal("0.10"))
    overfilled = default_candidate_deal(volume=Decimal("0.12"))
    updated = _advance(tracked, (overfilled,), as_of=VALID_UNTIL + timedelta(days=1), history_covers_until=VALID_UNTIL)
    assert updated.matched_position_id is None
    assert updated.position_record.status is TradeStatus.PENDING
    assert updated.last_match_outcome is MT5MatchOutcome.VOLUME_MISMATCH


def test_advance_malformed_history_never_becomes_not_filled() -> None:
    tracked = default_tracked_recommendation()
    updated = _advance(tracked, (), as_of=VALID_UNTIL + timedelta(days=1), history_read_status="MALFORMED_TIMESTAMP")
    assert updated.position_record.status is TradeStatus.PENDING


def test_advance_later_successful_read_resolves_after_prior_outage() -> None:
    tracked = default_tracked_recommendation()
    outaged = _advance(tracked, (), as_of=SIGNAL_TIME + timedelta(minutes=1), history_read_status="UNAVAILABLE")
    resolved = _advance(outaged, (default_candidate_deal(),), as_of=SIGNAL_TIME + timedelta(minutes=2))
    assert resolved.matched_position_id == 7001
    assert resolved.position_record.status is TradeStatus.OPEN


def test_advance_ambiguous_leaves_position_record_non_terminal() -> None:
    tracked = default_tracked_recommendation()
    first = default_candidate_deal(ticket=1, position_id=1001)
    second = default_candidate_deal(ticket=2, position_id=1002)
    updated = _advance(tracked, (first, second))
    assert updated.matched_position_id is None
    assert updated.last_match_outcome is MT5MatchOutcome.AMBIGUOUS
    assert updated.position_record.status is TradeStatus.PENDING


def test_advance_ambiguous_at_expiry_still_never_fabricates_a_winner() -> None:
    tracked = default_tracked_recommendation()
    first = default_candidate_deal(ticket=1, position_id=1001)
    second = default_candidate_deal(ticket=2, position_id=1002)
    updated = _advance(tracked, (first, second), as_of=VALID_UNTIL + timedelta(minutes=1), history_covers_until=VALID_UNTIL)
    assert updated.matched_position_id is None
    assert updated.position_record.status is TradeStatus.PENDING


# --- match immutability across cycles / restart ---


def test_matched_position_id_never_changes_once_set() -> None:
    tracked = default_tracked_recommendation()
    matched = _advance(tracked, (default_candidate_deal(),))
    assert matched.matched_position_id == 7001

    decoy = default_candidate_deal(ticket=99, position_id=42, time=SIGNAL_TIME + timedelta(minutes=2))
    again = _advance(matched, (default_candidate_deal(), decoy), as_of=SIGNAL_TIME + timedelta(minutes=3))
    assert again.matched_position_id == 7001


def test_matching_never_reruns_once_matched_even_with_a_better_looking_candidate() -> None:
    """The caller always re-queries the complete history from signal_time
    onward (never a narrower window) - the originally-matched deal is
    always present in every subsequent read alongside anything new."""
    tracked = default_tracked_recommendation()
    original = default_candidate_deal()
    matched = _advance(tracked, (original,))

    other_position_same_everything = default_candidate_deal(ticket=55, position_id=8888, time=SIGNAL_TIME + timedelta(minutes=2))
    again = _advance(matched, (original, other_position_same_everything), as_of=SIGNAL_TIME + timedelta(minutes=3))
    assert again.matched_position_id == 7001
    assert again.position_record.status in (TradeStatus.OPEN, TradeStatus.WIN, TradeStatus.LOSS, TradeStatus.BREAKEVEN)


def test_restart_before_fill_resumes_identically() -> None:
    tracked = default_tracked_recommendation()
    persisted_snapshot = tracked.model_copy(deep=True)
    updated = _advance(persisted_snapshot, (default_candidate_deal(),))
    assert updated.matched_position_id == 7001


def test_restart_while_open_recomputes_identically() -> None:
    tracked = default_tracked_recommendation()
    matched = _advance(tracked, (default_candidate_deal(),))
    restarted_copy = matched.model_copy(deep=True)
    again = _advance(restarted_copy, (default_candidate_deal(),), as_of=SIGNAL_TIME + timedelta(minutes=2))
    assert again.matched_position_id == matched.matched_position_id
    assert again.position_record.status is TradeStatus.OPEN


def test_restart_after_terminal_persistence_stays_terminal() -> None:
    tracked = default_tracked_recommendation()
    entry = default_candidate_deal(ticket=1)
    exit_deal = default_candidate_deal(ticket=2, entry=MT5DealEntry.OUT, time=SIGNAL_TIME + timedelta(minutes=2), profit=Decimal("50"))
    terminal = _advance(tracked, (entry, exit_deal), as_of=SIGNAL_TIME + timedelta(minutes=3), history_covers_until=SIGNAL_TIME + timedelta(minutes=3))
    assert terminal.position_record.status is TradeStatus.WIN

    restarted = terminal.model_copy(deep=True)
    again = _advance(restarted, (entry, exit_deal), as_of=SIGNAL_TIME + timedelta(minutes=10), history_covers_until=SIGNAL_TIME + timedelta(minutes=10))
    assert again.position_record.status is TradeStatus.WIN
    assert again.position_record.pnl == terminal.position_record.pnl


def test_repeated_identical_history_produces_identical_terminal_state() -> None:
    tracked = default_tracked_recommendation()
    entry = default_candidate_deal(ticket=1)
    exit_deal = default_candidate_deal(ticket=2, entry=MT5DealEntry.OUT, time=SIGNAL_TIME + timedelta(minutes=2), profit=Decimal("-30"))
    first = _advance(tracked, (entry, exit_deal), as_of=SIGNAL_TIME + timedelta(minutes=3), history_covers_until=SIGNAL_TIME + timedelta(minutes=3))
    second = _advance(tracked, (entry, exit_deal), as_of=SIGNAL_TIME + timedelta(minutes=3), history_covers_until=SIGNAL_TIME + timedelta(minutes=3))
    assert first == second


# --- manual / unrelated trade separation ---


def test_unrelated_manual_position_does_not_mutate_position_record() -> None:
    tracked = default_tracked_recommendation()
    unrelated_manual_trade = default_candidate_deal(symbol="XAUUSD", position_id=55555)
    updated = _advance(tracked, (unrelated_manual_trade,))
    assert updated.matched_position_id is None
    assert updated.position_record.status is TradeStatus.PENDING


def test_unmatched_deal_never_becomes_ai_statistics_record() -> None:
    """A deal that would otherwise qualify, but belongs to a position_id
    already claimed by another recommendation, must never mutate this
    recommendation's record."""
    tracked = default_tracked_recommendation()
    already_claimed = default_candidate_deal(position_id=42)
    updated = _advance(tracked, (already_claimed,), already_claimed_position_ids=(42,))
    assert updated.matched_position_id is None
    assert updated.position_record.status is TradeStatus.PENDING


def test_matched_position_alone_updates_recommendation_record() -> None:
    tracked = default_tracked_recommendation()
    matched = _advance(tracked, (default_candidate_deal(),))
    assert matched.position_record.trade_id == tracked.position_record.trade_id
    assert matched.matched_position_id == 7001
