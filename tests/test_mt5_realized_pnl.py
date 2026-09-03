"""Stage 10D pure ``compute_realized_daily_pnl``: exact approved formula
(commission+fee on every trading deal, profit+swap on OUT/INOUT only),
non-trading exclusion, OUT_BY/UNKNOWN fail-closed, half-open window,
malformed-timestamp fail-closed, determinism."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.core.enums.mt5_history import MT5DealEntry, MT5DealType, MT5RealizedPnLBlockReason, MT5RealizedPnLOutcome
from app.mt5.history import compute_realized_daily_pnl
from tests.mt5_history_support import NOW, WINDOW_END, WINDOW_START, default_deal

TRADING_DAY_KEY = "2026-01-01"


def _compute(*deals):
    return compute_realized_daily_pnl(
        as_of=NOW, trading_day_key=TRADING_DAY_KEY, deals=tuple(deals), window_start=WINDOW_START, window_end=WINDOW_END
    )


# --- confirmed empty ---


def test_no_deals_is_exact_zero() -> None:
    result = _compute()
    assert result.outcome is MT5RealizedPnLOutcome.READY
    assert result.realized_daily_pnl == Decimal("0")


def test_only_non_trading_deals_is_exact_zero() -> None:
    result = _compute(default_deal(deal_type=MT5DealType.NON_TRADING, symbol=None, profit=Decimal("500")))
    assert result.outcome is MT5RealizedPnLOutcome.READY
    assert result.realized_daily_pnl == Decimal("0")


# --- profitable / losing OUT ---


def test_profitable_out_deal() -> None:
    result = _compute(
        default_deal(deal_type=MT5DealType.BUY, entry=MT5DealEntry.OUT, profit=Decimal("100"), commission=Decimal("-2"), swap=Decimal("-1"), fee=Decimal("-0.5"))
    )
    assert result.outcome is MT5RealizedPnLOutcome.READY
    assert result.realized_daily_pnl == Decimal("96.5")


def test_losing_out_deal() -> None:
    result = _compute(
        default_deal(deal_type=MT5DealType.SELL, entry=MT5DealEntry.OUT, profit=Decimal("-100"), commission=Decimal("-2"), swap=Decimal("-1"), fee=Decimal("-0.5"))
    )
    assert result.outcome is MT5RealizedPnLOutcome.READY
    assert result.realized_daily_pnl == Decimal("-103.5")


# --- IN: commission + fee only ---


def test_in_deal_contributes_commission_only() -> None:
    result = _compute(default_deal(deal_type=MT5DealType.BUY, entry=MT5DealEntry.IN, commission=Decimal("-3"), profit=Decimal("999"), swap=Decimal("999")))
    assert result.realized_daily_pnl == Decimal("-3")


def test_in_deal_contributes_fee_too() -> None:
    result = _compute(default_deal(deal_type=MT5DealType.BUY, entry=MT5DealEntry.IN, commission=Decimal("-3"), fee=Decimal("-1")))
    assert result.realized_daily_pnl == Decimal("-4")


def test_in_deal_ignores_profit_and_swap() -> None:
    result = _compute(default_deal(deal_type=MT5DealType.BUY, entry=MT5DealEntry.IN, commission=Decimal("0"), fee=Decimal("0"), profit=Decimal("1000"), swap=Decimal("1000")))
    assert result.realized_daily_pnl == Decimal("0")


# --- OUT: all four components ---


def test_out_deal_full_component_matrix() -> None:
    result = _compute(
        default_deal(deal_type=MT5DealType.BUY, entry=MT5DealEntry.OUT, profit=Decimal("50"), commission=Decimal("-4"), swap=Decimal("-2"), fee=Decimal("-1"))
    )
    assert result.realized_daily_pnl == Decimal("43")


# --- INOUT: full booked economics once ---


def test_inout_deal_contributes_full_economics_once() -> None:
    result = _compute(
        default_deal(deal_type=MT5DealType.SELL, entry=MT5DealEntry.INOUT, profit=Decimal("20"), commission=Decimal("-1"), swap=Decimal("-0.5"), fee=Decimal("-0.25"))
    )
    assert result.realized_daily_pnl == Decimal("18.25")


# --- multiple entry fills / multiple closing fills / partial close ---


def test_multiple_entry_fills_each_contribute_own_commission_and_fee() -> None:
    result = _compute(
        default_deal(ticket=1, deal_type=MT5DealType.BUY, entry=MT5DealEntry.IN, commission=Decimal("-1"), fee=Decimal("-0.1")),
        default_deal(ticket=2, deal_type=MT5DealType.BUY, entry=MT5DealEntry.IN, commission=Decimal("-1"), fee=Decimal("-0.1")),
    )
    assert result.realized_daily_pnl == Decimal("-2.2")


def test_multiple_closing_fills_each_contribute_independently() -> None:
    result = _compute(
        default_deal(ticket=1, deal_type=MT5DealType.SELL, entry=MT5DealEntry.OUT, profit=Decimal("30"), commission=Decimal("-1")),
        default_deal(ticket=2, deal_type=MT5DealType.SELL, entry=MT5DealEntry.OUT, profit=Decimal("-10"), commission=Decimal("-1")),
    )
    assert result.realized_daily_pnl == Decimal("18")


def test_partial_close_sums_correctly() -> None:
    """One IN (open) plus two partial OUT deals - flat per-deal summation,
    no lifecycle reconstruction."""
    result = _compute(
        default_deal(ticket=1, deal_type=MT5DealType.BUY, entry=MT5DealEntry.IN, commission=Decimal("-2")),
        default_deal(ticket=2, deal_type=MT5DealType.BUY, entry=MT5DealEntry.OUT, profit=Decimal("40"), commission=Decimal("-1")),
        default_deal(ticket=3, deal_type=MT5DealType.BUY, entry=MT5DealEntry.OUT, profit=Decimal("15"), commission=Decimal("-1")),
    )
    assert result.realized_daily_pnl == Decimal("51")


def test_mixed_profitable_and_loss_deals() -> None:
    result = _compute(
        default_deal(ticket=1, deal_type=MT5DealType.BUY, entry=MT5DealEntry.OUT, profit=Decimal("100")),
        default_deal(ticket=2, deal_type=MT5DealType.SELL, entry=MT5DealEntry.OUT, profit=Decimal("-40")),
    )
    assert result.realized_daily_pnl == Decimal("60")


# --- non-trading exclusion ---


def test_deposit_like_balance_deal_excluded() -> None:
    result = _compute(default_deal(deal_type=MT5DealType.NON_TRADING, symbol=None, profit=Decimal("10000")))
    assert result.realized_daily_pnl == Decimal("0")


def test_withdrawal_credit_correction_bonus_all_excluded() -> None:
    deals = [
        default_deal(ticket=i, deal_type=MT5DealType.NON_TRADING, symbol=None, profit=amount)
        for i, amount in enumerate((Decimal("-500"), Decimal("1000"), Decimal("50"), Decimal("25")), start=1)
    ]
    result = _compute(*deals)
    assert result.realized_daily_pnl == Decimal("0")


# --- OUT_BY fail-closed ---


def test_out_by_blocks_whole_assessment() -> None:
    result = _compute(default_deal(deal_type=MT5DealType.BUY, entry=MT5DealEntry.OUT_BY))
    assert result.outcome is MT5RealizedPnLOutcome.BLOCKED
    assert result.realized_daily_pnl is None
    assert result.blocked_reasons == (MT5RealizedPnLBlockReason.UNSUPPORTED_OUT_BY,)


def test_out_by_blocks_even_alongside_other_profitable_deals() -> None:
    result = _compute(
        default_deal(ticket=1, deal_type=MT5DealType.BUY, entry=MT5DealEntry.OUT, profit=Decimal("1000")),
        default_deal(ticket=2, deal_type=MT5DealType.SELL, entry=MT5DealEntry.OUT_BY),
    )
    assert result.outcome is MT5RealizedPnLOutcome.BLOCKED
    assert result.realized_daily_pnl is None


# --- UNKNOWN fail-closed ---


def test_unknown_deal_type_blocks() -> None:
    result = _compute(default_deal(deal_type=MT5DealType.UNKNOWN))
    assert result.outcome is MT5RealizedPnLOutcome.BLOCKED
    assert result.blocked_reasons == (MT5RealizedPnLBlockReason.UNMAPPABLE_DEAL_TYPE,)


def test_unknown_entry_on_buy_sell_blocks() -> None:
    result = _compute(default_deal(deal_type=MT5DealType.BUY, entry=MT5DealEntry.UNKNOWN))
    assert result.outcome is MT5RealizedPnLOutcome.BLOCKED
    assert result.blocked_reasons == (MT5RealizedPnLBlockReason.UNMAPPABLE_DEAL_ENTRY,)


# --- no partial PnL when blocked ---


def test_no_partial_pnl_returned_when_blocked() -> None:
    result = _compute(
        default_deal(ticket=1, deal_type=MT5DealType.BUY, entry=MT5DealEntry.OUT, profit=Decimal("500")),
        default_deal(ticket=2, deal_type=MT5DealType.UNKNOWN),
    )
    assert result.outcome is MT5RealizedPnLOutcome.BLOCKED
    assert result.realized_daily_pnl is None


# --- deterministic reason / ticket ordering ---


def test_deterministic_reason_order_independent_of_input_order() -> None:
    forward = _compute(
        default_deal(ticket=1, deal_type=MT5DealType.BUY, entry=MT5DealEntry.OUT_BY),
        default_deal(ticket=2, deal_type=MT5DealType.UNKNOWN),
    )
    backward = _compute(
        default_deal(ticket=2, deal_type=MT5DealType.UNKNOWN),
        default_deal(ticket=1, deal_type=MT5DealType.BUY, entry=MT5DealEntry.OUT_BY),
    )
    assert forward.blocked_reasons == backward.blocked_reasons
    assert forward.blocked_reasons == (MT5RealizedPnLBlockReason.UNMAPPABLE_DEAL_TYPE, MT5RealizedPnLBlockReason.UNSUPPORTED_OUT_BY)


def test_unsafe_ticket_set_matches_input_order() -> None:
    result = _compute(
        default_deal(ticket=10, deal_type=MT5DealType.BUY, entry=MT5DealEntry.OUT, profit=Decimal("1")),
        default_deal(ticket=20, deal_type=MT5DealType.UNKNOWN),
        default_deal(ticket=30, deal_type=MT5DealType.BUY, entry=MT5DealEntry.OUT_BY),
    )
    assert result.unsafe_deal_tickets == (20, 30)


# --- repeated input gives identical result ---


def test_repeated_identical_input_gives_identical_output() -> None:
    deals = (
        default_deal(ticket=1, deal_type=MT5DealType.BUY, entry=MT5DealEntry.IN, commission=Decimal("-1")),
        default_deal(ticket=2, deal_type=MT5DealType.BUY, entry=MT5DealEntry.OUT, profit=Decimal("25"), commission=Decimal("-1")),
    )
    first = _compute(*deals)
    second = _compute(*deals)
    assert first == second


# --- half-open trading-day window boundary ---


def test_deal_exactly_at_window_start_included() -> None:
    result = _compute(default_deal(time=WINDOW_START, deal_type=MT5DealType.BUY, entry=MT5DealEntry.OUT, profit=Decimal("10")))
    assert result.realized_daily_pnl == Decimal("10")


def test_deal_exactly_at_window_end_excluded() -> None:
    result = _compute(default_deal(time=WINDOW_END, deal_type=MT5DealType.BUY, entry=MT5DealEntry.OUT, profit=Decimal("10")))
    assert result.realized_daily_pnl == Decimal("0")


def test_deal_before_window_excluded() -> None:
    result = _compute(
        default_deal(time=WINDOW_START - timedelta(microseconds=1), deal_type=MT5DealType.BUY, entry=MT5DealEntry.OUT, profit=Decimal("10"))
    )
    assert result.realized_daily_pnl == Decimal("0")


def test_deal_after_window_excluded() -> None:
    result = _compute(
        default_deal(time=WINDOW_END + timedelta(microseconds=1), deal_type=MT5DealType.BUY, entry=MT5DealEntry.OUT, profit=Decimal("10"))
    )
    assert result.realized_daily_pnl == Decimal("0")


def test_deals_outside_window_never_trigger_unmappable_block() -> None:
    """A deal that would be unmappable, but sits entirely outside the
    window, never even gets classified - it does not contribute and does
    not block."""
    result = _compute(
        default_deal(time=WINDOW_END + timedelta(days=1), deal_type=MT5DealType.UNKNOWN),
        default_deal(deal_type=MT5DealType.BUY, entry=MT5DealEntry.OUT, profit=Decimal("5")),
    )
    assert result.outcome is MT5RealizedPnLOutcome.READY
    assert result.realized_daily_pnl == Decimal("5")


# --- unavailable != zero (typed at the model/outcome layer) ---


def test_unavailable_is_not_representable_as_ready_zero() -> None:
    """BLOCKED (unsafe) and READY-zero (confirmed-empty) are structurally
    distinct outcomes - a caller can never mistake one for the other."""
    blocked = _compute(default_deal(deal_type=MT5DealType.UNKNOWN))
    empty = _compute()
    assert blocked.outcome is not empty.outcome
    assert blocked.realized_daily_pnl is None
    assert empty.realized_daily_pnl == Decimal("0")


# --- malformed timestamp ---


def test_malformed_timestamp_blocks_regardless_of_window() -> None:
    """A deal at/before the Unix epoch is MT5's own "unset" sentinel having
    survived normalization - checked before window membership, so it
    cannot be dodged by appearing to be outside the window."""
    result = _compute(default_deal(time=datetime(1969, 12, 31, tzinfo=UTC), deal_type=MT5DealType.NON_TRADING, symbol=None))
    assert result.outcome is MT5RealizedPnLOutcome.BLOCKED
    assert result.blocked_reasons == (MT5RealizedPnLBlockReason.MALFORMED_TIMESTAMP,)


def test_malformed_timestamp_at_exact_epoch_blocks() -> None:
    result = _compute(default_deal(time=datetime(1970, 1, 1, tzinfo=UTC), deal_type=MT5DealType.NON_TRADING, symbol=None))
    assert result.outcome is MT5RealizedPnLOutcome.BLOCKED
    assert result.blocked_reasons == (MT5RealizedPnLBlockReason.MALFORMED_TIMESTAMP,)


# --- architecture: pure module hygiene ---


def test_history_module_never_imports_metatrader5() -> None:
    import ast
    import inspect

    import app.mt5.history as history_module

    tree = ast.parse(inspect.getsource(history_module))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    assert names.isdisjoint({"MetaTrader5", "app.mt5.client", "pathlib", "os"})


def test_history_module_source_never_calls_wall_clock() -> None:
    import ast
    import inspect

    import app.mt5.history as history_module

    tree = ast.parse(inspect.getsource(history_module))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in {"now", "utcnow"}, "pure history module must not read the wall clock"
