"""Stage 9 ``StatisticsAggregator``: deterministic ``PositionRecord`` history
aggregation into ``PerformanceSnapshot``. Reporting only - covered
separately by ``tests/test_statistics_no_influence_on_session.py``.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.config import SIGNAL_EXECUTION_WINDOW
from app.core.enums import MarketType, TradeDirection, TradeStatus
from app.core.models import PositionRecord
from app.statistics.aggregator import StatisticsAggregator


def _record(now: datetime, **overrides: object) -> PositionRecord:
    fields: dict[str, object] = {
        "trade_id": "T-1",
        "symbol": "TEST",
        "market": MarketType.FX,
        "direction": TradeDirection.LONG,
        "signal_time": now,
        "valid_until": now + SIGNAL_EXECUTION_WINDOW,
        "status": TradeStatus.PENDING,
        "planned_entry": Decimal("100"),
        "stop_loss": Decimal("99"),
    }
    fields.update(overrides)
    return PositionRecord(**fields)


def test_zero_history_yields_defaults() -> None:
    snapshot = StatisticsAggregator().aggregate(records=())
    assert snapshot.total_trades == 0
    assert snapshot.wins == 0
    assert snapshot.losses == 0
    assert snapshot.breakeven == 0
    assert snapshot.not_filled == 0
    assert snapshot.expired == 0
    assert snapshot.win_rate is None
    assert snapshot.profit_factor is None
    assert snapshot.expectancy is None
    assert snapshot.max_drawdown is None


def test_wins_counted(now: datetime) -> None:
    records = (
        _record(now, trade_id="T-1", status=TradeStatus.WIN, pnl=Decimal("100")),
        _record(now, trade_id="T-2", status=TradeStatus.WIN, pnl=Decimal("50")),
    )
    snapshot = StatisticsAggregator().aggregate(records=records)
    assert snapshot.wins == 2
    assert snapshot.total_trades == 2
    assert snapshot.win_rate == 1.0


def test_losses_counted(now: datetime) -> None:
    records = (_record(now, trade_id="T-1", status=TradeStatus.LOSS, pnl=Decimal("-40")),)
    snapshot = StatisticsAggregator().aggregate(records=records)
    assert snapshot.losses == 1
    assert snapshot.total_trades == 1
    assert snapshot.win_rate == 0.0


def test_breakeven_counted(now: datetime) -> None:
    records = (_record(now, trade_id="T-1", status=TradeStatus.BREAKEVEN, pnl=Decimal("0")),)
    snapshot = StatisticsAggregator().aggregate(records=records)
    assert snapshot.breakeven == 1
    assert snapshot.total_trades == 1


def test_not_filled_counted(now: datetime) -> None:
    records = (_record(now, trade_id="T-1", status=TradeStatus.NOT_FILLED),)
    snapshot = StatisticsAggregator().aggregate(records=records)
    assert snapshot.not_filled == 1
    assert snapshot.total_trades == 1


def test_expired_counted(now: datetime) -> None:
    records = (_record(now, trade_id="T-1", status=TradeStatus.EXPIRED),)
    snapshot = StatisticsAggregator().aggregate(records=records)
    assert snapshot.expired == 1
    assert snapshot.total_trades == 1


@pytest.mark.parametrize(
    "status", [TradeStatus.PENDING, TradeStatus.FILLED, TradeStatus.OPEN, TradeStatus.CLOSED, TradeStatus.CANCELLED]
)
def test_non_terminal_statuses_excluded_from_all_counts(now: datetime, status: TradeStatus) -> None:
    """PerformanceSnapshot has no bucket for these statuses - counting them
    would silently invent one, so they are excluded entirely rather than
    mis-attributed."""
    records = (_record(now, trade_id="T-1", status=status),)
    snapshot = StatisticsAggregator().aggregate(records=records)
    assert snapshot.total_trades == 0


def test_mixed_records_field_consistency(now: datetime) -> None:
    records = (
        _record(now, trade_id="T-1", status=TradeStatus.WIN, pnl=Decimal("100")),
        _record(now, trade_id="T-2", status=TradeStatus.WIN, pnl=Decimal("50")),
        _record(now, trade_id="T-3", status=TradeStatus.LOSS, pnl=Decimal("-40")),
        _record(now, trade_id="T-4", status=TradeStatus.BREAKEVEN, pnl=Decimal("0")),
        _record(now, trade_id="T-5", status=TradeStatus.NOT_FILLED),
        _record(now, trade_id="T-6", status=TradeStatus.EXPIRED),
        _record(now, trade_id="T-7", status=TradeStatus.PENDING),
    )
    snapshot = StatisticsAggregator().aggregate(records=records)
    assert snapshot.wins == 2
    assert snapshot.losses == 1
    assert snapshot.breakeven == 1
    assert snapshot.not_filled == 1
    assert snapshot.expired == 1
    assert snapshot.total_trades == snapshot.wins + snapshot.losses + snapshot.breakeven + snapshot.not_filled + snapshot.expired
    assert snapshot.total_trades == 6  # T-7 (PENDING) excluded


def test_win_rate_fraction_of_total_trades(now: datetime) -> None:
    records = (
        _record(now, trade_id="T-1", status=TradeStatus.WIN, pnl=Decimal("10")),
        _record(now, trade_id="T-2", status=TradeStatus.LOSS, pnl=Decimal("-10")),
        _record(now, trade_id="T-3", status=TradeStatus.LOSS, pnl=Decimal("-10")),
        _record(now, trade_id="T-4", status=TradeStatus.BREAKEVEN, pnl=Decimal("0")),
    )
    snapshot = StatisticsAggregator().aggregate(records=records)
    assert snapshot.win_rate == pytest.approx(0.25)


def test_profit_factor_ratio_of_gross_profit_to_gross_loss(now: datetime) -> None:
    records = (
        _record(now, trade_id="T-1", status=TradeStatus.WIN, pnl=Decimal("300")),
        _record(now, trade_id="T-2", status=TradeStatus.LOSS, pnl=Decimal("-100")),
    )
    snapshot = StatisticsAggregator().aggregate(records=records)
    assert snapshot.profit_factor == pytest.approx(3.0)


def test_profit_factor_undefined_with_zero_losses(now: datetime) -> None:
    records = (_record(now, trade_id="T-1", status=TradeStatus.WIN, pnl=Decimal("100")),)
    snapshot = StatisticsAggregator().aggregate(records=records)
    assert snapshot.profit_factor is None


def test_expectancy_average_pnl_across_pnl_bearing_records(now: datetime) -> None:
    records = (
        _record(now, trade_id="T-1", status=TradeStatus.WIN, pnl=Decimal("100")),
        _record(now, trade_id="T-2", status=TradeStatus.LOSS, pnl=Decimal("-40")),
        _record(now, trade_id="T-3", status=TradeStatus.NOT_FILLED),  # no pnl - excluded from the average
    )
    snapshot = StatisticsAggregator().aggregate(records=records)
    assert snapshot.expectancy == Decimal("30")  # (100 + -40) / 2


def test_max_drawdown_never_computed_in_v1(now: datetime) -> None:
    """Design blocker: no starting-equity baseline is available to this
    aggregator and no safe, order-independent chronological key exists
    across all counted TradeStatus values - see app.statistics.aggregator's
    module docstring."""
    records = (_record(now, trade_id="T-1", status=TradeStatus.LOSS, pnl=Decimal("-9999999")),)
    snapshot = StatisticsAggregator().aggregate(records=records)
    assert snapshot.max_drawdown is None


def test_deterministic_repeated_calls(now: datetime) -> None:
    records = (
        _record(now, trade_id="T-1", status=TradeStatus.WIN, pnl=Decimal("100")),
        _record(now, trade_id="T-2", status=TradeStatus.LOSS, pnl=Decimal("-40")),
    )
    first = StatisticsAggregator().aggregate(records=records)
    second = StatisticsAggregator().aggregate(records=records)
    assert first == second


def test_malformed_position_record_rejected_by_existing_model(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _record(now, valid_until=now)  # valid_until must be after signal_time - PositionRecord's own invariant


def test_mutating_record_after_construction_still_validated(now: datetime) -> None:
    record = _record(now)
    with pytest.raises(ValidationError):
        record.status = "NOT_A_REAL_STATUS"
