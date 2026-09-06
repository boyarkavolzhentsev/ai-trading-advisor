"""Part F NETTING/UNKNOWN issuance guard - pure unit tests (Final Runtime
Integration, Part F corrective design).

Tests ``app.orchestration.runtime_cycle._evaluate_netting_guard`` and
``_symbol_has_unresolved_tracking`` directly - no MT5 client, no
filesystem, no full runtime cycle needed for this deterministic,
already-existing-facts-only guard.
"""

from __future__ import annotations

from app.core.enums.mt5_runtime import AccountPositionMode
from app.core.enums.runtime_cycle import NettingIssuanceOutcome
from app.core.enums.trade import TradeStatus
from app.core.models.mt5_position import MT5Position
from app.core.enums.order import OrderSide
from decimal import Decimal
from app.orchestration.runtime_cycle import _evaluate_netting_guard, _symbol_has_unresolved_tracking
from tests.mt5_matching_support import SIGNAL_TIME, default_position_record, default_tracked_recommendation

SYMBOL = "BTCUSDT"


def _position(symbol: str = SYMBOL, ticket: int = 555) -> MT5Position:
    return MT5Position(
        as_of=SIGNAL_TIME,
        ticket=ticket,
        symbol=symbol,
        side=OrderSide.BUY,
        volume=Decimal("1"),
        price_open=Decimal("100"),
        price_current=Decimal("101"),
    )


def _tracked(trade_id: str, *, symbol: str = SYMBOL, status: TradeStatus = TradeStatus.PENDING, matched_position_id: int | None = None):
    overrides: dict[str, object] = {"trade_id": trade_id, "symbol": symbol, "status": status}
    tracked_overrides: dict[str, object] = {"position_record": default_position_record(**overrides)}
    if matched_position_id is not None:
        tracked_overrides["matched_position_id"] = matched_position_id
    return default_tracked_recommendation(**tracked_overrides)


# --- _symbol_has_unresolved_tracking: terminal/nonterminal classification ---


def test_pending_status_holds_lock() -> None:
    tracked = {"t1": _tracked("t1", status=TradeStatus.PENDING)}
    assert _symbol_has_unresolved_tracking(tracked, SYMBOL) is True


def test_open_status_holds_lock() -> None:
    tracked = {"t1": _tracked("t1", status=TradeStatus.OPEN, matched_position_id=7001)}
    assert _symbol_has_unresolved_tracking(tracked, SYMBOL) is True


def test_not_filled_status_releases_lock() -> None:
    tracked = {"t1": _tracked("t1", status=TradeStatus.NOT_FILLED)}
    assert _symbol_has_unresolved_tracking(tracked, SYMBOL) is False


def test_win_status_releases_lock() -> None:
    tracked = {"t1": _tracked("t1", status=TradeStatus.WIN, matched_position_id=7001)}
    assert _symbol_has_unresolved_tracking(tracked, SYMBOL) is False


def test_loss_status_releases_lock() -> None:
    tracked = {"t1": _tracked("t1", status=TradeStatus.LOSS, matched_position_id=7001)}
    assert _symbol_has_unresolved_tracking(tracked, SYMBOL) is False


def test_breakeven_status_releases_lock() -> None:
    tracked = {"t1": _tracked("t1", status=TradeStatus.BREAKEVEN, matched_position_id=7001)}
    assert _symbol_has_unresolved_tracking(tracked, SYMBOL) is False


def test_unrelated_symbol_never_blocks() -> None:
    tracked = {"t1": _tracked("t1", symbol="ETHUSDT", status=TradeStatus.PENDING)}
    assert _symbol_has_unresolved_tracking(tracked, SYMBOL) is False


# --- _evaluate_netting_guard: full scenario matrix ---


def test_flat_no_unresolved_one_actionable_allowed() -> None:
    result = _evaluate_netting_guard(
        symbol=SYMBOL,
        account_position_mode=AccountPositionMode.NETTING,
        positions_read_status="OK",
        positions=(),
        tracked_by_trade_id={},
        actionable_count=1,
    )
    assert result.outcome is NettingIssuanceOutcome.ALLOWED
    assert result.account_position_mode is AccountPositionMode.NETTING
    assert result.symbol == SYMBOL


def test_flat_no_unresolved_multiple_actionable_all_blocked() -> None:
    result = _evaluate_netting_guard(
        symbol=SYMBOL,
        account_position_mode=AccountPositionMode.NETTING,
        positions_read_status="OK",
        positions=(),
        tracked_by_trade_id={},
        actionable_count=3,
    )
    assert result.outcome is NettingIssuanceOutcome.BLOCKED_MULTIPLE_ACTIONABLE_RECOMMENDATIONS


def test_zero_actionable_is_not_a_safety_block() -> None:
    result = _evaluate_netting_guard(
        symbol=SYMBOL,
        account_position_mode=AccountPositionMode.NETTING,
        positions_read_status="OK",
        positions=(),
        tracked_by_trade_id={},
        actionable_count=0,
    )
    assert result.outcome is NettingIssuanceOutcome.NO_ACTIONABLE_RECOMMENDATIONS


def test_existing_broker_position_blocks_even_one_actionable() -> None:
    result = _evaluate_netting_guard(
        symbol=SYMBOL,
        account_position_mode=AccountPositionMode.NETTING,
        positions_read_status="OK",
        positions=(_position(),),
        tracked_by_trade_id={},
        actionable_count=1,
    )
    assert result.outcome is NettingIssuanceOutcome.BLOCKED_EXISTING_BROKER_POSITION


def test_existing_broker_position_blocks_multiple_actionable_too() -> None:
    result = _evaluate_netting_guard(
        symbol=SYMBOL,
        account_position_mode=AccountPositionMode.NETTING,
        positions_read_status="OK",
        positions=(_position(),),
        tracked_by_trade_id={},
        actionable_count=3,
    )
    assert result.outcome is NettingIssuanceOutcome.BLOCKED_EXISTING_BROKER_POSITION


def test_pending_tracked_recommendation_blocks_new_issuance() -> None:
    result = _evaluate_netting_guard(
        symbol=SYMBOL,
        account_position_mode=AccountPositionMode.NETTING,
        positions_read_status="OK",
        positions=(),
        tracked_by_trade_id={"t1": _tracked("t1", status=TradeStatus.PENDING)},
        actionable_count=1,
    )
    assert result.outcome is NettingIssuanceOutcome.BLOCKED_EXISTING_UNRESOLVED_RECOMMENDATION


def test_open_tracked_recommendation_blocks_new_issuance() -> None:
    result = _evaluate_netting_guard(
        symbol=SYMBOL,
        account_position_mode=AccountPositionMode.NETTING,
        positions_read_status="OK",
        positions=(),
        tracked_by_trade_id={"t1": _tracked("t1", status=TradeStatus.OPEN, matched_position_id=7001)},
        actionable_count=1,
    )
    assert result.outcome is NettingIssuanceOutcome.BLOCKED_EXISTING_UNRESOLVED_RECOMMENDATION


def test_terminal_not_filled_releases_lock_and_allows() -> None:
    result = _evaluate_netting_guard(
        symbol=SYMBOL,
        account_position_mode=AccountPositionMode.NETTING,
        positions_read_status="OK",
        positions=(),
        tracked_by_trade_id={"t1": _tracked("t1", status=TradeStatus.NOT_FILLED)},
        actionable_count=1,
    )
    assert result.outcome is NettingIssuanceOutcome.ALLOWED


def test_terminal_win_releases_lock_and_allows() -> None:
    result = _evaluate_netting_guard(
        symbol=SYMBOL,
        account_position_mode=AccountPositionMode.NETTING,
        positions_read_status="OK",
        positions=(),
        tracked_by_trade_id={"t1": _tracked("t1", status=TradeStatus.WIN, matched_position_id=7001)},
        actionable_count=1,
    )
    assert result.outcome is NettingIssuanceOutcome.ALLOWED


def test_terminal_loss_releases_lock_and_allows() -> None:
    result = _evaluate_netting_guard(
        symbol=SYMBOL,
        account_position_mode=AccountPositionMode.NETTING,
        positions_read_status="OK",
        positions=(),
        tracked_by_trade_id={"t1": _tracked("t1", status=TradeStatus.LOSS, matched_position_id=7001)},
        actionable_count=1,
    )
    assert result.outcome is NettingIssuanceOutcome.ALLOWED


def test_terminal_breakeven_releases_lock_and_allows() -> None:
    result = _evaluate_netting_guard(
        symbol=SYMBOL,
        account_position_mode=AccountPositionMode.NETTING,
        positions_read_status="OK",
        positions=(),
        tracked_by_trade_id={"t1": _tracked("t1", status=TradeStatus.BREAKEVEN, matched_position_id=7001)},
        actionable_count=1,
    )
    assert result.outcome is NettingIssuanceOutcome.ALLOWED


def test_unrelated_symbol_nonterminal_tracked_does_not_block() -> None:
    result = _evaluate_netting_guard(
        symbol=SYMBOL,
        account_position_mode=AccountPositionMode.NETTING,
        positions_read_status="OK",
        positions=(),
        tracked_by_trade_id={"t1": _tracked("t1", symbol="ETHUSDT", status=TradeStatus.OPEN, matched_position_id=7001)},
        actionable_count=1,
    )
    assert result.outcome is NettingIssuanceOutcome.ALLOWED


def test_unavailable_positions_defers_to_existing_snapshot_unavailable_path() -> None:
    """When the positions snapshot itself is not confirmed OK, this guard
    applies no netting-specific reason - it lets the call proceed so Stage
    10E's own existing SNAPSHOT_UNAVAILABLE fail-closed path (already
    audited) governs, rather than inventing a duplicate reason."""
    result = _evaluate_netting_guard(
        symbol=SYMBOL,
        account_position_mode=AccountPositionMode.NETTING,
        positions_read_status="UNAVAILABLE",
        positions=(),
        tracked_by_trade_id={},
        actionable_count=1,
    )
    assert result.outcome is NettingIssuanceOutcome.ALLOWED


# --- UNKNOWN uses identical restrictions to NETTING ---


def test_unknown_mode_multiple_actionable_blocked_like_netting() -> None:
    result = _evaluate_netting_guard(
        symbol=SYMBOL,
        account_position_mode=AccountPositionMode.UNKNOWN,
        positions_read_status="OK",
        positions=(),
        tracked_by_trade_id={},
        actionable_count=2,
    )
    assert result.outcome is NettingIssuanceOutcome.BLOCKED_MULTIPLE_ACTIONABLE_RECOMMENDATIONS
    assert result.account_position_mode is AccountPositionMode.UNKNOWN


def test_unknown_mode_existing_position_blocked_like_netting() -> None:
    result = _evaluate_netting_guard(
        symbol=SYMBOL,
        account_position_mode=AccountPositionMode.UNKNOWN,
        positions_read_status="OK",
        positions=(_position(),),
        tracked_by_trade_id={},
        actionable_count=1,
    )
    assert result.outcome is NettingIssuanceOutcome.BLOCKED_EXISTING_BROKER_POSITION


def test_unknown_mode_flat_and_uncontested_allows_single_actionable() -> None:
    result = _evaluate_netting_guard(
        symbol=SYMBOL,
        account_position_mode=AccountPositionMode.UNKNOWN,
        positions_read_status="OK",
        positions=(),
        tracked_by_trade_id={},
        actionable_count=1,
    )
    assert result.outcome is NettingIssuanceOutcome.ALLOWED


def test_unknown_mode_never_produces_hedging_shaped_result() -> None:
    """UNKNOWN with multiple actionable must never behave like HEDGING
    (which would allow all of them through unrestricted)."""
    result = _evaluate_netting_guard(
        symbol=SYMBOL,
        account_position_mode=AccountPositionMode.UNKNOWN,
        positions_read_status="OK",
        positions=(),
        tracked_by_trade_id={},
        actionable_count=5,
    )
    assert result.outcome is not NettingIssuanceOutcome.ALLOWED


# --- family order cannot select a winner ---


def test_actionable_count_alone_drives_outcome_not_family_identity() -> None:
    """The guard never inspects which families are actionable - only the
    count - so no family ordering/identity can influence block/allow."""
    result_forward = _evaluate_netting_guard(
        symbol=SYMBOL, account_position_mode=AccountPositionMode.NETTING, positions_read_status="OK",
        positions=(), tracked_by_trade_id={}, actionable_count=2,
    )
    result_same_count = _evaluate_netting_guard(
        symbol=SYMBOL, account_position_mode=AccountPositionMode.NETTING, positions_read_status="OK",
        positions=(), tracked_by_trade_id={}, actionable_count=2,
    )
    assert result_forward.outcome == result_same_count.outcome == NettingIssuanceOutcome.BLOCKED_MULTIPLE_ACTIONABLE_RECOMMENDATIONS
