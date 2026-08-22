"""Quote and instrument metadata contract rules."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.enums import InstrumentStatus
from app.core.models import BidAskQuote, InstrumentMetadata, PriceQuote


def _bid_ask(now: datetime, **overrides: object) -> BidAskQuote:
    fields: dict[str, object] = {
        "symbol": "BTCUSDT",
        "bid": Decimal("100"),
        "ask": Decimal("101"),
        "timestamp": now,
        "source": "binance:book_ticker",
    }
    fields.update(overrides)
    return BidAskQuote(**fields)


def _metadata(now: datetime, **overrides: object) -> InstrumentMetadata:
    fields: dict[str, object] = {
        "symbol": "BTCUSDT",
        "base_asset": "BTC",
        "quote_asset": "USDT",
        "status": InstrumentStatus.TRADING,
        "tick_size": Decimal("0.01"),
        "price_precision": 2,
        "step_size": Decimal("0.00001"),
        "quantity_precision": 5,
        "source": "binance:exchange_info",
        "timestamp": now,
    }
    fields.update(overrides)
    return InstrumentMetadata(**fields)


def test_price_quote_keeps_decimal_precision(now: datetime) -> None:
    quote = PriceQuote(
        symbol="BTCUSDT",
        price=Decimal("12345.67890123"),
        timestamp=now,
        source="binance:ticker_price",
    )
    assert quote.price == Decimal("12345.67890123")
    assert quote.timestamp.tzinfo is not None


def test_price_quote_rejects_naive_timestamp() -> None:
    with pytest.raises(ValidationError):
        PriceQuote(
            symbol="BTCUSDT",
            price=Decimal("1"),
            timestamp=datetime(2026, 1, 2, 12, 0),
            source="binance:ticker_price",
        )


def test_price_quote_requires_source(now: datetime) -> None:
    with pytest.raises(ValidationError):
        PriceQuote(symbol="BTCUSDT", price=Decimal("1"), timestamp=now, source="")


def test_bid_ask_spread(now: datetime) -> None:
    quote = _bid_ask(now, bid=Decimal("100.10"), ask=Decimal("100.40"))
    assert quote.spread == Decimal("0.30")


def test_bid_ask_allows_equal_bid_and_ask(now: datetime) -> None:
    assert _bid_ask(now, ask=Decimal("100")).spread == Decimal("0")


def test_bid_ask_rejects_crossed_quote(now: datetime) -> None:
    with pytest.raises(ValidationError, match="ask must be greater than or equal to bid"):
        _bid_ask(now, bid=Decimal("101"), ask=Decimal("100"))


def test_bid_ask_rejects_negative_price(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _bid_ask(now, bid=Decimal("-1"))


def test_bid_ask_quantities_are_optional(now: datetime) -> None:
    quote = _bid_ask(now)
    assert quote.bid_quantity is None
    assert quote.ask_quantity is None


def test_bid_ask_is_immutable(now: datetime) -> None:
    quote = _bid_ask(now)
    with pytest.raises(ValidationError):
        quote.bid = Decimal("1")


def test_instrument_metadata_accepts_optional_bounds(now: datetime) -> None:
    metadata = _metadata(
        now,
        min_quantity=Decimal("0.00001"),
        max_quantity=Decimal("9000"),
        min_notional=Decimal("5"),
    )
    assert metadata.min_quantity == Decimal("0.00001")
    assert metadata.max_quantity == Decimal("9000")
    assert metadata.min_notional == Decimal("5")


def test_instrument_metadata_rejects_inverted_quantity_bounds(now: datetime) -> None:
    with pytest.raises(ValidationError, match="max_quantity must be greater"):
        _metadata(now, min_quantity=Decimal("10"), max_quantity=Decimal("1"))


def test_instrument_metadata_rejects_zero_tick_size(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _metadata(now, tick_size=Decimal("0"))


def test_instrument_metadata_rejects_unknown_field(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _metadata(now, contract_size=Decimal("1"))


def test_instrument_status_values() -> None:
    assert InstrumentStatus.TRADING == "TRADING"
    assert set(InstrumentStatus) == {
        InstrumentStatus.TRADING,
        InstrumentStatus.HALTED,
        InstrumentStatus.CLOSED,
        InstrumentStatus.UNKNOWN,
    }


def test_timestamps_are_normalized_to_utc_awareness() -> None:
    quote = PriceQuote(
        symbol="BTCUSDT",
        price=Decimal("1"),
        timestamp=datetime(2026, 1, 2, 12, 0, tzinfo=UTC),
        source="binance:ticker_price",
    )
    assert quote.timestamp.utcoffset() is not None
