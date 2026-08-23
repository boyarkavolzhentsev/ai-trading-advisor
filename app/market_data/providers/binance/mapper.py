"""Binance payload -> internal contract normalization.

Pure functions only: no HTTP, no decisions, no business logic. Anything that
does not fit the expected shape raises ``InvalidProviderResponseError`` instead
of being guessed at or repaired. Generic payload parsing lives in
``app.market_data.parsing``; this module holds only what is specific to
Binance's field names and vocabulary.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from app.core.enums.instrument import InstrumentStatus
from app.core.enums.market import Timeframe
from app.core.models.candle import OHLCVCandle
from app.core.models.instrument import InstrumentMetadata
from app.core.models.quote import BidAskQuote, PriceQuote
from app.market_data.exceptions import (
    InvalidProviderResponseError,
    UnknownSymbolError,
    UnsupportedTimeframeError,
)
from app.market_data.parsing import (
    as_decimal,
    as_mapping,
    as_optional_decimal,
    as_str,
    build,
    normalize_symbol,
    timestamp_from_millis,
    to_decimal,
)
from app.market_data.providers.binance.constants import (
    INSTRUMENT_STATUSES,
    LOT_SIZE_FILTER,
    MIN_NOTIONAL_FILTER,
    NOTIONAL_FILTER,
    PRICE_FILTER,
    TIMEFRAME_INTERVALS,
)

KLINE_MIN_FIELDS = 6
"""open time, open, high, low, close, volume — the fields this stage uses."""


@dataclass(frozen=True, slots=True)
class NormalizedBookTicker:
    """Book ticker after parsing, before quality validation.

    Exists so the bid/ask relationship can be judged by the validator before a
    domain model (which would reject it outright) is constructed.
    """

    symbol: str
    bid: Decimal
    ask: Decimal
    bid_quantity: Decimal | None
    ask_quantity: Decimal | None


def to_binance_interval(timeframe: Timeframe) -> str:
    """Map an internal timeframe onto a Binance interval string.

    Raises:
        UnsupportedTimeframeError: if the timeframe is not supported yet.
    """
    try:
        return TIMEFRAME_INTERVALS[timeframe]
    except KeyError as exc:
        supported = ", ".join(sorted(tf.value for tf in TIMEFRAME_INTERVALS))
        raise UnsupportedTimeframeError(
            f"binance provider does not support timeframe {timeframe.value}; supported: {supported}"
        ) from exc


def map_price_quote(payload: Any, *, source: str, fetched_at: datetime) -> PriceQuote:
    """Map a ``/ticker/price`` payload onto ``PriceQuote``.

    The endpoint reports no timestamp, so the fetch time is used.
    """
    body = as_mapping(payload, "ticker price")
    return build(
        PriceQuote,
        "ticker price",
        symbol=as_str(body, "symbol", "ticker price"),
        price=as_decimal(body, "price", "ticker price"),
        timestamp=fetched_at,
        source=source,
    )


def normalize_book_ticker(payload: Any) -> NormalizedBookTicker:
    """Parse a ``/ticker/bookTicker`` payload into normalized primitives."""
    body = as_mapping(payload, "book ticker")
    return NormalizedBookTicker(
        symbol=as_str(body, "symbol", "book ticker"),
        bid=as_decimal(body, "bidPrice", "book ticker"),
        ask=as_decimal(body, "askPrice", "book ticker"),
        bid_quantity=as_optional_decimal(body, "bidQty", "book ticker"),
        ask_quantity=as_optional_decimal(body, "askQty", "book ticker"),
    )


def to_bid_ask_quote(
    ticker: NormalizedBookTicker,
    *,
    source: str,
    fetched_at: datetime,
) -> BidAskQuote:
    """Build the domain quote from an already validated book ticker."""
    return build(
        BidAskQuote,
        "book ticker",
        symbol=ticker.symbol,
        bid=ticker.bid,
        ask=ticker.ask,
        bid_quantity=ticker.bid_quantity,
        ask_quantity=ticker.ask_quantity,
        timestamp=fetched_at,
        source=source,
    )


def map_klines(payload: Any) -> list[OHLCVCandle]:
    """Map a ``/klines`` payload onto candles, preserving Binance's order.

    Binance returns rows as ``[openTime, open, high, low, close, volume, ...]``
    with the open time in milliseconds. The candle timestamp is the open time.
    """
    if not isinstance(payload, Sequence) or isinstance(payload, str | bytes):
        raise InvalidProviderResponseError(
            f"klines payload must be a list, got {type(payload).__name__}"
        )

    candles: list[OHLCVCandle] = []
    for index, row in enumerate(payload):
        if not isinstance(row, Sequence) or isinstance(row, str | bytes):
            raise InvalidProviderResponseError(
                f"klines row {index} must be a list, got {type(row).__name__}"
            )
        if len(row) < KLINE_MIN_FIELDS:
            raise InvalidProviderResponseError(
                f"klines row {index} has {len(row)} fields, expected at least {KLINE_MIN_FIELDS}"
            )
        candles.append(
            build(
                OHLCVCandle,
                f"klines row {index}",
                timestamp=timestamp_from_millis(row[0], f"klines row {index} open time"),
                open=to_decimal(row[1], f"klines row {index} open"),
                high=to_decimal(row[2], f"klines row {index} high"),
                low=to_decimal(row[3], f"klines row {index} low"),
                close=to_decimal(row[4], f"klines row {index} close"),
                volume=to_decimal(row[5], f"klines row {index} volume"),
            )
        )
    return candles


def extract_server_time(payload: Any) -> datetime | None:
    """Return ``serverTime`` from an ``/exchangeInfo`` payload if present."""
    if isinstance(payload, Mapping) and "serverTime" in payload:
        return timestamp_from_millis(payload["serverTime"], "exchange info server time")
    return None


def map_instrument_metadata(
    payload: Any,
    *,
    symbol: str,
    source: str,
    fetched_at: datetime,
) -> InstrumentMetadata:
    """Map an ``/exchangeInfo`` payload onto ``InstrumentMetadata``.

    Raises:
        UnknownSymbolError: if the payload describes no such symbol.
        InvalidProviderResponseError: if the entry or its filters are unusable.
    """
    body = as_mapping(payload, "exchange info")
    entries = body.get("symbols")
    if not isinstance(entries, Sequence) or isinstance(entries, str | bytes):
        raise InvalidProviderResponseError("exchange info payload has no 'symbols' list")

    entry = next(
        (
            candidate
            for candidate in entries
            if isinstance(candidate, Mapping) and candidate.get("symbol") == symbol
        ),
        None,
    )
    if entry is None:
        raise UnknownSymbolError(f"binance exchange info does not describe symbol {symbol!r}")

    filters = _filters_by_type(entry, symbol)
    price_filter = filters.get(PRICE_FILTER)
    lot_filter = filters.get(LOT_SIZE_FILTER)
    if price_filter is None or lot_filter is None:
        raise InvalidProviderResponseError(
            f"exchange info for {symbol} is missing {PRICE_FILTER} or {LOT_SIZE_FILTER}"
        )
    notional_filter = filters.get(NOTIONAL_FILTER) or filters.get(MIN_NOTIONAL_FILTER) or {}

    tick_size = as_decimal(price_filter, "tickSize", f"{PRICE_FILTER} of {symbol}")
    step_size = as_decimal(lot_filter, "stepSize", f"{LOT_SIZE_FILTER} of {symbol}")

    return build(
        InstrumentMetadata,
        f"exchange info for {symbol}",
        symbol=as_str(entry, "symbol", f"exchange info for {symbol}"),
        base_asset=as_str(entry, "baseAsset", f"exchange info for {symbol}"),
        quote_asset=as_str(entry, "quoteAsset", f"exchange info for {symbol}"),
        status=_map_status(entry.get("status")),
        tick_size=tick_size,
        price_precision=_precision_of(tick_size),
        step_size=step_size,
        quantity_precision=_precision_of(step_size),
        min_quantity=as_optional_decimal(lot_filter, "minQty", f"{LOT_SIZE_FILTER} of {symbol}"),
        max_quantity=as_optional_decimal(lot_filter, "maxQty", f"{LOT_SIZE_FILTER} of {symbol}"),
        min_notional=as_optional_decimal(notional_filter, "minNotional", f"notional of {symbol}"),
        source=source,
        timestamp=extract_server_time(body) or fetched_at,
    )


def _map_status(raw: Any) -> InstrumentStatus:
    """Map a Binance symbol status onto the internal enum, defaulting to UNKNOWN."""
    if not isinstance(raw, str):
        return InstrumentStatus.UNKNOWN
    return INSTRUMENT_STATUSES.get(raw.upper(), InstrumentStatus.UNKNOWN)


def _filters_by_type(entry: Mapping[str, Any], symbol: str) -> dict[str, Mapping[str, Any]]:
    """Index an exchange-info symbol entry's filters by ``filterType``."""
    raw_filters = entry.get("filters", [])
    if not isinstance(raw_filters, Sequence) or isinstance(raw_filters, str | bytes):
        raise InvalidProviderResponseError(f"exchange info for {symbol} has unusable 'filters'")
    return {
        item["filterType"]: item
        for item in raw_filters
        if isinstance(item, Mapping) and isinstance(item.get("filterType"), str)
    }


def _precision_of(step: Decimal) -> int:
    """Number of decimal places implied by a tick or step size."""
    exponent = step.normalize().as_tuple().exponent
    if not isinstance(exponent, int):  # NaN / Infinity
        raise InvalidProviderResponseError(f"step size {step} is not a finite number")
    return max(0, -exponent)


__all__ = [
    "NormalizedBookTicker",
    "extract_server_time",
    "map_instrument_metadata",
    "map_klines",
    "map_price_quote",
    "normalize_book_ticker",
    "normalize_symbol",
    "to_bid_ask_quote",
    "to_binance_interval",
]
