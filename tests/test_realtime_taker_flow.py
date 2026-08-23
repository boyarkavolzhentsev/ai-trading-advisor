"""TakerFlowAggregator bucket-closing behaviour."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.core.enums.instrument import ContractType
from app.core.enums.market import Timeframe
from app.core.enums.order import OrderSide
from app.core.models.trade_event import TradeEvent
from app.market_data.realtime.taker_flow import TakerFlowAggregator

SOURCE = "binance_futures:agg_trade"


def _trade(timestamp: datetime, side: OrderSide, quantity: str, quote: str | None = None) -> TradeEvent:
    return TradeEvent(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        trade_id=1,
        price=Decimal("100"),
        quantity=Decimal(quantity),
        quote_quantity=Decimal(quote) if quote is not None else None,
        side=side,
        timestamp=timestamp,
        source=SOURCE,
    )


def _aggregator(timeframe: Timeframe = Timeframe.M1) -> TakerFlowAggregator:
    return TakerFlowAggregator(
        symbol="BTCUSDT", contract_type=ContractType.PERPETUAL, timeframe=timeframe, source=SOURCE
    )


def test_trades_within_one_bucket_accumulate_without_closing() -> None:
    aggregator = _aggregator()
    start = datetime(2026, 1, 2, 12, 0, 0, tzinfo=UTC)
    assert aggregator.add_trade(_trade(start, OrderSide.BUY, "1")) is None
    assert aggregator.add_trade(_trade(start + timedelta(seconds=10), OrderSide.SELL, "2")) is None

    closed = aggregator.flush()
    assert closed is not None
    assert closed.buy_volume == Decimal("1")
    assert closed.sell_volume == Decimal("2")
    assert closed.symbol == "BTCUSDT"
    assert closed.timeframe is Timeframe.M1


def test_a_trade_in_the_next_bucket_closes_the_previous_one() -> None:
    aggregator = _aggregator()
    start = datetime(2026, 1, 2, 12, 0, 0, tzinfo=UTC)
    aggregator.add_trade(_trade(start, OrderSide.BUY, "3"))

    closed = aggregator.add_trade(_trade(start + timedelta(minutes=1), OrderSide.BUY, "5"))

    assert closed is not None
    assert closed.buy_volume == Decimal("3")
    assert closed.sell_volume == Decimal("0")
    assert closed.timestamp == start.replace(second=0, microsecond=0)


def test_total_delta_and_buy_ratio_still_hold_on_realtime_snapshots() -> None:
    aggregator = _aggregator()
    start = datetime(2026, 1, 2, 12, 0, 0, tzinfo=UTC)
    aggregator.add_trade(_trade(start, OrderSide.BUY, "7"))
    aggregator.add_trade(_trade(start, OrderSide.SELL, "3"))
    closed = aggregator.flush()

    assert closed is not None
    assert closed.total_volume == Decimal("10")
    assert closed.delta == Decimal("4")
    assert closed.buy_ratio == 0.7


def test_buy_quote_volume_accumulates_only_for_buy_side() -> None:
    aggregator = _aggregator()
    start = datetime(2026, 1, 2, 12, 0, 0, tzinfo=UTC)
    aggregator.add_trade(_trade(start, OrderSide.BUY, "2", quote="200"))
    aggregator.add_trade(_trade(start, OrderSide.SELL, "1", quote="100"))
    closed = aggregator.flush()

    assert closed is not None
    assert closed.buy_quote_volume == Decimal("200")


def test_buy_quote_volume_is_none_when_any_trade_lacks_it() -> None:
    aggregator = _aggregator()
    start = datetime(2026, 1, 2, 12, 0, 0, tzinfo=UTC)
    aggregator.add_trade(_trade(start, OrderSide.BUY, "2", quote="200"))
    aggregator.add_trade(_trade(start, OrderSide.BUY, "1", quote=None))
    closed = aggregator.flush()

    assert closed is not None
    assert closed.buy_quote_volume is None


def test_late_out_of_order_trade_for_a_closed_window_is_dropped() -> None:
    aggregator = _aggregator()
    start = datetime(2026, 1, 2, 12, 0, 0, tzinfo=UTC)
    aggregator.add_trade(_trade(start + timedelta(minutes=5), OrderSide.BUY, "1"))

    # A late trade timestamped before the current open bucket must not
    # reopen or corrupt it.
    result = aggregator.add_trade(_trade(start, OrderSide.SELL, "100"))
    assert result is None

    closed = aggregator.flush()
    assert closed is not None
    assert closed.buy_volume == Decimal("1")
    assert closed.sell_volume == Decimal("0")


def test_flush_with_no_open_bucket_returns_none() -> None:
    aggregator = _aggregator()
    assert aggregator.flush() is None


def test_bucket_start_is_aligned_to_timeframe_boundary() -> None:
    aggregator = _aggregator(Timeframe.M5)
    mid_bucket = datetime(2026, 1, 2, 12, 3, 27, tzinfo=UTC)
    aggregator.add_trade(_trade(mid_bucket, OrderSide.BUY, "1"))
    closed = aggregator.flush()
    assert closed is not None
    assert closed.timestamp == datetime(2026, 1, 2, 12, 0, 0, tzinfo=UTC)
