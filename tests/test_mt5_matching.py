"""Stage 10E pure ``match_recommendation``: exact hard constraints, price
never blocking, zero/one/multiple candidate semantics, determinism."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from app.core.enums.mt5_history import MT5DealEntry, MT5DealType
from app.core.enums.mt5_matching import MT5MatchOutcome
from app.core.enums.trade import TradeDirection
from app.mt5.matching import match_recommendation
from tests.mt5_matching_support import SIGNAL_TIME, VALID_UNTIL, default_candidate_deal

_DEFAULTS = dict(
    symbol="EURUSD",
    direction=TradeDirection.LONG,
    signal_time=SIGNAL_TIME,
    valid_until=VALID_UNTIL,
    approved_broker_volume=Decimal("1"),
    pre_existing_position_ids=(),
    already_claimed_position_ids=(),
    history_read_status="OK",
)


def _match(*deals, as_of=None, history_covers_until=None, **overrides):
    kwargs = {**_DEFAULTS, **overrides}
    return match_recommendation(
        as_of=as_of or VALID_UNTIL,
        deals=tuple(deals),
        history_covers_until=history_covers_until or VALID_UNTIL,
        **kwargs,
    )


# --- unique match ---


def test_unique_exact_match() -> None:
    result = _match(default_candidate_deal())
    assert result.outcome is MT5MatchOutcome.MATCHED
    assert result.matched_position_id == 7001


def test_wrong_symbol_excluded() -> None:
    result = _match(default_candidate_deal(symbol="XAUUSD"))
    assert result.outcome is MT5MatchOutcome.EXPIRED_CONFIRMED_UNFILLED


def test_wrong_direction_excluded() -> None:
    result = _match(default_candidate_deal(deal_type=MT5DealType.SELL))
    assert result.outcome is MT5MatchOutcome.EXPIRED_CONFIRMED_UNFILLED


def test_out_entry_not_a_candidate() -> None:
    result = _match(default_candidate_deal(entry=MT5DealEntry.OUT))
    assert result.outcome is MT5MatchOutcome.EXPIRED_CONFIRMED_UNFILLED


def test_inout_entry_not_a_candidate() -> None:
    result = _match(default_candidate_deal(entry=MT5DealEntry.INOUT))
    assert result.outcome is MT5MatchOutcome.EXPIRED_CONFIRMED_UNFILLED


def test_out_by_entry_not_a_candidate() -> None:
    result = _match(default_candidate_deal(entry=MT5DealEntry.OUT_BY))
    assert result.outcome is MT5MatchOutcome.EXPIRED_CONFIRMED_UNFILLED


def test_non_trading_deal_not_a_candidate() -> None:
    result = _match(default_candidate_deal(deal_type=MT5DealType.NON_TRADING, symbol=None, entry=MT5DealEntry.IN))
    assert result.outcome is MT5MatchOutcome.EXPIRED_CONFIRMED_UNFILLED


# --- window boundary ---


def test_event_before_signal_time_excluded() -> None:
    result = _match(default_candidate_deal(time=SIGNAL_TIME - timedelta(microseconds=1)))
    assert result.outcome is MT5MatchOutcome.EXPIRED_CONFIRMED_UNFILLED


def test_event_exactly_at_signal_time_included() -> None:
    result = _match(default_candidate_deal(time=SIGNAL_TIME))
    assert result.outcome is MT5MatchOutcome.MATCHED


def test_event_exactly_at_valid_until_included() -> None:
    result = _match(default_candidate_deal(time=VALID_UNTIL))
    assert result.outcome is MT5MatchOutcome.MATCHED


def test_event_after_valid_until_excluded() -> None:
    result = _match(default_candidate_deal(time=VALID_UNTIL + timedelta(microseconds=1)))
    assert result.outcome is MT5MatchOutcome.EXPIRED_CONFIRMED_UNFILLED


# --- volume ---


def test_wrong_volume_is_volume_mismatch_not_confirmed_unfilled() -> None:
    """Overfilled evidence is real broker activity - it must never be
    conflated with "no fill at all" (see the multi-fill correctness patch)."""
    result = _match(default_candidate_deal(volume=Decimal("2")))
    assert result.outcome is MT5MatchOutcome.VOLUME_MISMATCH


def test_exact_volume_matches() -> None:
    result = _match(default_candidate_deal(volume=Decimal("0.10")), approved_broker_volume=Decimal("0.1"))
    assert result.outcome is MT5MatchOutcome.MATCHED


# --- price never blocks ---


def test_price_slippage_does_not_block_match() -> None:
    result = _match(default_candidate_deal(price=Decimal("103.5")))
    assert result.outcome is MT5MatchOutcome.MATCHED


# --- pre-existing / already-claimed ---


def test_pre_existing_position_rejected() -> None:
    result = _match(default_candidate_deal(), pre_existing_position_ids=(7001,))
    assert result.outcome is MT5MatchOutcome.EXPIRED_CONFIRMED_UNFILLED


def test_already_claimed_position_rejected() -> None:
    result = _match(default_candidate_deal(), already_claimed_position_ids=(7001,))
    assert result.outcome is MT5MatchOutcome.EXPIRED_CONFIRMED_UNFILLED


def test_pre_existing_of_a_different_position_id_does_not_block() -> None:
    result = _match(default_candidate_deal(), pre_existing_position_ids=(9999,))
    assert result.outcome is MT5MatchOutcome.MATCHED


# --- consistency check: earliest deal for its position_id ---


def test_add_to_existing_position_id_rejected_when_earlier_deal_present() -> None:
    """An IN deal that is NOT the earliest deal on record for its
    position_id (an earlier deal for that id exists in the supplied
    history) is rejected even if not caught by the pre-existing snapshot."""
    earlier = default_candidate_deal(ticket=1, time=SIGNAL_TIME - timedelta(days=1))
    later_in = default_candidate_deal(ticket=2, time=SIGNAL_TIME + timedelta(minutes=1))
    result = _match(earlier, later_in)
    assert result.outcome is MT5MatchOutcome.EXPIRED_CONFIRMED_UNFILLED


# --- zero / one / multiple candidates ---


def test_zero_candidates_before_expiry_is_no_candidate_yet() -> None:
    result = _match(as_of=SIGNAL_TIME + timedelta(minutes=1), history_covers_until=SIGNAL_TIME + timedelta(minutes=1))
    assert result.outcome is MT5MatchOutcome.NO_CANDIDATE_YET


def test_zero_candidates_after_expiry_with_full_coverage_is_expired_confirmed_unfilled() -> None:
    result = _match(as_of=VALID_UNTIL + timedelta(minutes=1), history_covers_until=VALID_UNTIL)
    assert result.outcome is MT5MatchOutcome.EXPIRED_CONFIRMED_UNFILLED


def test_zero_candidates_after_expiry_with_partial_coverage_is_no_candidate_yet() -> None:
    """The read succeeded ("OK") but did not reach far enough to confirm
    the complete window - never conflated with a confirmed-unfilled read."""
    result = _match(as_of=VALID_UNTIL + timedelta(minutes=1), history_covers_until=VALID_UNTIL - timedelta(minutes=1))
    assert result.outcome is MT5MatchOutcome.NO_CANDIDATE_YET


def test_unique_candidate_is_matched() -> None:
    result = _match(default_candidate_deal())
    assert result.outcome is MT5MatchOutcome.MATCHED


def test_multiple_candidates_is_ambiguous() -> None:
    first = default_candidate_deal(ticket=1, position_id=1001)
    second = default_candidate_deal(ticket=2, position_id=1002)
    result = _match(first, second)
    assert result.outcome is MT5MatchOutcome.AMBIGUOUS
    assert result.candidate_position_ids == (1001, 1002)


def test_ambiguous_no_arbitrary_winner_regardless_of_input_order() -> None:
    first = default_candidate_deal(ticket=1, position_id=2002)
    second = default_candidate_deal(ticket=2, position_id=1001)
    forward = _match(first, second)
    backward = _match(second, first)
    assert forward.outcome is MT5MatchOutcome.AMBIGUOUS
    assert forward.candidate_position_ids == backward.candidate_position_ids == (1001, 2002)


def test_multiple_fills_same_position_id_sum_to_approved_volume_is_matched() -> None:
    """Two IN deals sharing the same position_id (scaling in) whose volumes
    sum exactly to approved_broker_volume are one MATCHED candidate
    lifecycle, not two, and not a volume mismatch."""
    first = default_candidate_deal(ticket=1, volume=Decimal("0.5"), time=SIGNAL_TIME + timedelta(minutes=1))
    second = default_candidate_deal(ticket=2, volume=Decimal("0.5"), time=SIGNAL_TIME + timedelta(minutes=2))
    result = _match(first, second)
    assert result.outcome is MT5MatchOutcome.MATCHED
    assert result.matched_position_id == 7001


# --- multi-fill / partial-fill matching correctness patch (required tests A-K) ---


def _fill(ticket: int, volume: str, minute: int, position_id: int = 7001) -> object:
    return default_candidate_deal(ticket=ticket, position_id=position_id, volume=Decimal(volume), time=SIGNAL_TIME + timedelta(minutes=minute))


def test_a_single_fill_exactly_equal_to_approved_is_matched() -> None:
    result = _match(_fill(1, "0.10", 1), approved_broker_volume=Decimal("0.10"))
    assert result.outcome is MT5MatchOutcome.MATCHED
    assert result.matched_position_id == 7001


def test_b_two_fills_summing_exactly_to_approved_is_matched() -> None:
    result = _match(_fill(1, "0.04", 1), _fill(2, "0.06", 2), approved_broker_volume=Decimal("0.10"))
    assert result.outcome is MT5MatchOutcome.MATCHED
    assert result.matched_position_id == 7001


def test_c_three_fills_summing_exactly_to_approved_is_matched() -> None:
    result = _match(_fill(1, "0.03", 1), _fill(2, "0.03", 2), _fill(3, "0.04", 3), approved_broker_volume=Decimal("0.10"))
    assert result.outcome is MT5MatchOutcome.MATCHED
    assert result.matched_position_id == 7001


def test_d_single_partial_fill_before_expiry_is_partial_fill_never_not_filled() -> None:
    result = _match(
        _fill(1, "0.04", 1),
        approved_broker_volume=Decimal("0.10"),
        as_of=SIGNAL_TIME + timedelta(minutes=2),
        history_covers_until=SIGNAL_TIME + timedelta(minutes=2),
    )
    assert result.outcome is MT5MatchOutcome.PARTIAL_FILL
    assert result.candidate_position_ids == (7001,)
    assert result.outcome is not MT5MatchOutcome.EXPIRED_CONFIRMED_UNFILLED


def test_e_partial_fill_after_expiry_with_confirmed_complete_history_still_not_not_filled() -> None:
    result = _match(
        _fill(1, "0.04", 1),
        approved_broker_volume=Decimal("0.10"),
        as_of=VALID_UNTIL + timedelta(minutes=1),
        history_covers_until=VALID_UNTIL,
    )
    assert result.outcome is MT5MatchOutcome.PARTIAL_FILL
    assert result.outcome is not MT5MatchOutcome.EXPIRED_CONFIRMED_UNFILLED


def test_f_partial_then_later_poll_with_complete_fills_transitions_to_matched() -> None:
    partial = _match(_fill(1, "0.04", 1), approved_broker_volume=Decimal("0.10"), as_of=SIGNAL_TIME + timedelta(minutes=2))
    assert partial.outcome is MT5MatchOutcome.PARTIAL_FILL

    complete = _match(
        _fill(1, "0.04", 1), _fill(2, "0.06", 2), approved_broker_volume=Decimal("0.10"), as_of=SIGNAL_TIME + timedelta(minutes=3)
    )
    assert complete.outcome is MT5MatchOutcome.MATCHED
    assert complete.matched_position_id == 7001


def test_g_overfill_is_volume_mismatch_never_matched_never_not_filled() -> None:
    result = _match(
        _fill(1, "0.12", 1),
        approved_broker_volume=Decimal("0.10"),
        as_of=VALID_UNTIL + timedelta(minutes=1),
        history_covers_until=VALID_UNTIL,
    )
    assert result.outcome is MT5MatchOutcome.VOLUME_MISMATCH
    assert result.outcome is not MT5MatchOutcome.MATCHED
    assert result.outcome is not MT5MatchOutcome.EXPIRED_CONFIRMED_UNFILLED
    assert result.candidate_position_ids == (7001,)


def test_h_two_position_ids_each_independently_reaching_approved_volume_is_ambiguous() -> None:
    result = _match(
        _fill(1, "0.10", 1, position_id=1001),
        _fill(2, "0.10", 2, position_id=1002),
        approved_broker_volume=Decimal("0.10"),
    )
    assert result.outcome is MT5MatchOutcome.AMBIGUOUS
    assert result.candidate_position_ids == (1001, 1002)


def test_i_two_fills_same_position_id_never_ambiguous() -> None:
    result = _match(_fill(1, "0.04", 1), _fill(2, "0.06", 2), approved_broker_volume=Decimal("0.10"))
    assert result.outcome is not MT5MatchOutcome.AMBIGUOUS
    assert result.outcome is MT5MatchOutcome.MATCHED


def test_j_input_order_does_not_change_grouped_result() -> None:
    a = _fill(1, "0.04", 1)
    b = _fill(2, "0.06", 2)
    forward = _match(a, b, approved_broker_volume=Decimal("0.10"))
    backward = _match(b, a, approved_broker_volume=Decimal("0.10"))
    assert forward == backward
    assert forward.outcome is MT5MatchOutcome.MATCHED


def test_k_exact_decimal_arithmetic_no_float_drift() -> None:
    """Decimal("0.1") + Decimal("0.1") + Decimal("0.1") == Decimal("0.3")
    exactly - the classic float-drift case (0.1+0.1+0.1 != 0.3 in binary
    floating point) must never surface here."""
    result = _match(
        _fill(1, "0.1", 1), _fill(2, "0.1", 2), _fill(3, "0.1", 3), approved_broker_volume=Decimal("0.3")
    )
    assert result.outcome is MT5MatchOutcome.MATCHED


# --- competing eligible lifecycle ownership (matching-precedence correction, required tests A-K) ---


def test_precedence_a_one_position_id_total_equals_approved_is_matched() -> None:
    result = _match(_fill(1, "0.10", 1, position_id=1001), approved_broker_volume=Decimal("0.10"))
    assert result.outcome is MT5MatchOutcome.MATCHED
    assert result.matched_position_id == 1001


def test_precedence_b_same_position_id_split_fills_still_matched() -> None:
    result = _match(
        _fill(1, "0.04", 1, position_id=1001), _fill(2, "0.06", 2, position_id=1001), approved_broker_volume=Decimal("0.10")
    )
    assert result.outcome is MT5MatchOutcome.MATCHED
    assert result.matched_position_id == 1001


def test_precedence_c_two_full_volume_lifecycles_is_ambiguous() -> None:
    result = _match(
        _fill(1, "0.10", 1, position_id=1001), _fill(2, "0.10", 2, position_id=2002), approved_broker_volume=Decimal("0.10")
    )
    assert result.outcome is MT5MatchOutcome.AMBIGUOUS
    assert result.candidate_position_ids == (1001, 2002)


def test_precedence_d_full_plus_partial_on_different_lifecycles_is_ambiguous() -> None:
    """The exact-volume lifecycle is NOT preferred over the partial one -
    both are structurally eligible, so ownership is unresolved."""
    result = _match(
        _fill(1, "0.10", 1, position_id=1001), _fill(2, "0.04", 2, position_id=2002), approved_broker_volume=Decimal("0.10")
    )
    assert result.outcome is MT5MatchOutcome.AMBIGUOUS
    assert result.candidate_position_ids == (1001, 2002)
    assert result.outcome is not MT5MatchOutcome.MATCHED


def test_precedence_e_full_plus_overfill_on_different_lifecycles_is_ambiguous() -> None:
    result = _match(
        _fill(1, "0.10", 1, position_id=1001), _fill(2, "0.12", 2, position_id=2002), approved_broker_volume=Decimal("0.10")
    )
    assert result.outcome is MT5MatchOutcome.AMBIGUOUS
    assert result.candidate_position_ids == (1001, 2002)
    assert result.outcome is not MT5MatchOutcome.MATCHED


def test_precedence_f_partial_plus_partial_on_different_lifecycles_is_ambiguous() -> None:
    result = _match(
        _fill(1, "0.04", 1, position_id=1001), _fill(2, "0.03", 2, position_id=2002), approved_broker_volume=Decimal("0.10")
    )
    assert result.outcome is MT5MatchOutcome.AMBIGUOUS
    assert result.candidate_position_ids == (1001, 2002)


def test_precedence_g_partial_plus_overfill_on_different_lifecycles_is_ambiguous() -> None:
    result = _match(
        _fill(1, "0.04", 1, position_id=1001), _fill(2, "0.12", 2, position_id=2002), approved_broker_volume=Decimal("0.10")
    )
    assert result.outcome is MT5MatchOutcome.AMBIGUOUS
    assert result.candidate_position_ids == (1001, 2002)


def test_precedence_g2_overfill_plus_overfill_on_different_lifecycles_is_ambiguous() -> None:
    result = _match(
        _fill(1, "0.12", 1, position_id=1001), _fill(2, "0.15", 2, position_id=2002), approved_broker_volume=Decimal("0.10")
    )
    assert result.outcome is MT5MatchOutcome.AMBIGUOUS
    assert result.candidate_position_ids == (1001, 2002)


def test_precedence_h_input_order_reversed_yields_identical_ambiguous_result() -> None:
    a = _fill(1, "0.10", 1, position_id=1001)
    b = _fill(2, "0.04", 2, position_id=2002)
    forward = _match(a, b, approved_broker_volume=Decimal("0.10"))
    backward = _match(b, a, approved_broker_volume=Decimal("0.10"))
    assert forward == backward
    assert forward.outcome is MT5MatchOutcome.AMBIGUOUS
    assert forward.candidate_position_ids == (1001, 2002)


def test_precedence_i_only_one_partial_lifecycle_is_partial_fill() -> None:
    result = _match(_fill(1, "0.04", 1, position_id=2002), approved_broker_volume=Decimal("0.10"))
    assert result.outcome is MT5MatchOutcome.PARTIAL_FILL
    assert result.candidate_position_ids == (2002,)


def test_precedence_j_only_one_overfilled_lifecycle_is_volume_mismatch() -> None:
    result = _match(_fill(1, "0.12", 1, position_id=2002), approved_broker_volume=Decimal("0.10"))
    assert result.outcome is MT5MatchOutcome.VOLUME_MISMATCH
    assert result.candidate_position_ids == (2002,)


def test_precedence_k_zero_lifecycle_semantics_unchanged() -> None:
    before_expiry = _match(as_of=SIGNAL_TIME + timedelta(minutes=1), history_covers_until=SIGNAL_TIME + timedelta(minutes=1))
    assert before_expiry.outcome is MT5MatchOutcome.NO_CANDIDATE_YET

    after_expiry_full_coverage = _match(as_of=VALID_UNTIL + timedelta(minutes=1), history_covers_until=VALID_UNTIL)
    assert after_expiry_full_coverage.outcome is MT5MatchOutcome.EXPIRED_CONFIRMED_UNFILLED


# --- MT5 unavailable ---


def test_read_unavailable_is_never_confirmed_unfilled() -> None:
    result = _match(as_of=VALID_UNTIL + timedelta(days=1), history_read_status="UNAVAILABLE")
    assert result.outcome is MT5MatchOutcome.READ_UNAVAILABLE


def test_malformed_timestamp_read_status_is_never_confirmed_unfilled() -> None:
    result = _match(as_of=VALID_UNTIL + timedelta(days=1), history_read_status="MALFORMED_TIMESTAMP")
    assert result.outcome is MT5MatchOutcome.READ_UNAVAILABLE


def test_read_unavailable_ignores_deals_entirely() -> None:
    """Even a deal that would otherwise MATCH is never used while the read
    itself is unavailable."""
    result = _match(default_candidate_deal(), history_read_status="UNAVAILABLE")
    assert result.outcome is MT5MatchOutcome.READ_UNAVAILABLE


# --- determinism ---


def test_repeated_identical_input_is_deterministic() -> None:
    deal = default_candidate_deal()
    first = _match(deal)
    second = _match(deal)
    assert first == second


def test_trade_after_validity_window_never_matched_even_if_unique() -> None:
    late_deal = default_candidate_deal(time=VALID_UNTIL + timedelta(minutes=10))
    result = _match(late_deal, as_of=VALID_UNTIL + timedelta(minutes=20), history_covers_until=VALID_UNTIL + timedelta(minutes=20))
    assert result.outcome is MT5MatchOutcome.EXPIRED_CONFIRMED_UNFILLED
