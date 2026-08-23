"""Binance USD-M perpetual futures payload -> internal contract normalization.

Pure functions only: no HTTP, no decisions, no business logic. Anything that
does not fit the expected shape raises ``InvalidProviderResponseError``
instead of being guessed at or repaired. Generic payload parsing lives in
``app.market_data.parsing``; this module holds only what is specific to
Binance's futures field names.

USD-M perpetual contracts only: no quarterly/delivery futures, no COIN-M.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from app.core.enums.instrument import ContractType
from app.core.enums.market import Timeframe
from app.core.models.funding import FundingRate
from app.core.models.open_interest import OpenInterest
from app.core.models.order_book import OrderBookLevel, OrderBookSnapshot
from app.core.models.taker_flow import TakerFlowSnapshot
from app.market_data.exceptions import InvalidProviderResponseError, UnsupportedTimeframeError
from app.market_data.parsing import (
    as_decimal,
    as_mapping,
    as_str,
    build,
    normalize_symbol,
    optional_timestamp_from_millis,
    timestamp_from_millis,
    to_decimal,
)
from app.market_data.providers.binance.futures.constants import (
    TAKER_FLOW_MIN_FIELDS,
    TIMEFRAME_INTERVALS,
)


def to_futures_interval(timeframe: Timeframe) -> str:
    """Map an internal timeframe onto a Binance futures interval string.

    Raises:
        UnsupportedTimeframeError: if the timeframe is not supported yet.
    """
    try:
        return TIMEFRAME_INTERVALS[timeframe]
    except KeyError as exc:
        supported = ", ".join(sorted(tf.value for tf in TIMEFRAME_INTERVALS))
        raise UnsupportedTimeframeError(
            f"binance futures provider does not support timeframe {timeframe.value}; "
            f"supported: {supported}"
        ) from exc


def extract_funding_interval_hours(payload: Any, symbol: str) -> int | None:
    """Return the venue-disclosed funding interval for ``symbol``, if any.

    Binance's ``fundingInfo`` endpoint lists only symbols whose funding
    interval deviates from the venue default; it does not disclose the
    default itself. A symbol absent from the list therefore yields ``None``
    rather than an assumed duration - the interval is genuinely unknown to
    this adapter.
    """
    if not isinstance(payload, Sequence) or isinstance(payload, str | bytes):
        raise InvalidProviderResponseError(
            f"funding info payload must be a list, got {type(payload).__name__}"
        )
    for entry in payload:
        if not (isinstance(entry, Mapping) and entry.get("symbol") == symbol):
            continue
        hours = entry.get("fundingIntervalHours")
        if isinstance(hours, bool) or not isinstance(hours, int) or hours <= 0:
            raise InvalidProviderResponseError(
                f"funding info for {symbol} has invalid fundingIntervalHours: {hours!r}"
            )
        return hours
    return None


def map_funding_rate(
    payload: Any,
    *,
    funding_interval_hours: int | None,
    source: str,
    fetched_at: datetime,
) -> FundingRate:
    """Map a ``/premiumIndex`` payload onto ``FundingRate``.

    Uses the venue's own ``time`` when present, falling back to the fetch
    time otherwise - the same policy as Spot's exchange-info mapping.
    """
    body = as_mapping(payload, "premium index")
    timestamp = optional_timestamp_from_millis(body.get("time"), "premium index time")
    return build(
        FundingRate,
        "premium index",
        symbol=as_str(body, "symbol", "premium index"),
        contract_type=ContractType.PERPETUAL,
        funding_rate=as_decimal(body, "lastFundingRate", "premium index"),
        funding_interval_hours=funding_interval_hours,
        mark_price=as_decimal(body, "markPrice", "premium index"),
        index_price=as_decimal(body, "indexPrice", "premium index"),
        next_funding_time=optional_timestamp_from_millis(
            body.get("nextFundingTime"), "premium index next funding time"
        ),
        source=source,
        timestamp=timestamp or fetched_at,
    )


def map_open_interest(payload: Any, *, source: str, fetched_at: datetime) -> OpenInterest:
    """Map an ``/openInterest`` payload onto ``OpenInterest``."""
    body = as_mapping(payload, "open interest")
    timestamp = optional_timestamp_from_millis(body.get("time"), "open interest time")
    return build(
        OpenInterest,
        "open interest",
        symbol=as_str(body, "symbol", "open interest"),
        contract_type=ContractType.PERPETUAL,
        open_interest=as_decimal(body, "openInterest", "open interest"),
        source=source,
        timestamp=timestamp or fetched_at,
    )


def map_taker_flow(
    payload: Any,
    *,
    symbol: str,
    timeframe: Timeframe,
    source: str,
) -> list[TakerFlowSnapshot]:
    """Map a futures ``/klines`` payload onto taker buy/sell volume snapshots.

    Binance does not report taker sell volume directly: it is normalized here
    as ``total volume - taker buy volume``, per row.
    """
    if not isinstance(payload, Sequence) or isinstance(payload, str | bytes):
        raise InvalidProviderResponseError(
            f"futures klines payload must be a list, got {type(payload).__name__}"
        )

    snapshots: list[TakerFlowSnapshot] = []
    for index, row in enumerate(payload):
        if not isinstance(row, Sequence) or isinstance(row, str | bytes):
            raise InvalidProviderResponseError(
                f"futures klines row {index} must be a list, got {type(row).__name__}"
            )
        if len(row) < TAKER_FLOW_MIN_FIELDS:
            raise InvalidProviderResponseError(
                f"futures klines row {index} has {len(row)} fields, "
                f"expected at least {TAKER_FLOW_MIN_FIELDS}"
            )
        total_volume = to_decimal(row[5], f"futures klines row {index} volume")
        taker_buy_volume = to_decimal(row[9], f"futures klines row {index} takerBuyBaseAssetVolume")
        taker_buy_quote_volume = to_decimal(
            row[10], f"futures klines row {index} takerBuyQuoteAssetVolume"
        )
        snapshots.append(
            build(
                TakerFlowSnapshot,
                f"futures klines row {index}",
                symbol=symbol,
                contract_type=ContractType.PERPETUAL,
                timeframe=timeframe,
                timestamp=timestamp_from_millis(row[0], f"futures klines row {index} open time"),
                buy_volume=taker_buy_volume,
                sell_volume=total_volume - taker_buy_volume,
                buy_quote_volume=taker_buy_quote_volume,
                source=source,
            )
        )
    return snapshots


def map_order_book_snapshot(
    payload: Any,
    *,
    symbol: str,
    source: str,
    fetched_at: datetime,
) -> OrderBookSnapshot:
    """Map a ``/depth`` payload onto a bounded ``OrderBookSnapshot``."""
    body = as_mapping(payload, "order book")
    last_update_id = body.get("lastUpdateId")
    if isinstance(last_update_id, bool) or not isinstance(last_update_id, int) or last_update_id < 0:
        raise InvalidProviderResponseError(
            f"order book has invalid lastUpdateId: {last_update_id!r}"
        )
    timestamp = optional_timestamp_from_millis(body.get("T"), "order book transaction time")
    return build(
        OrderBookSnapshot,
        "order book",
        symbol=symbol,
        contract_type=ContractType.PERPETUAL,
        last_update_id=last_update_id,
        bids=_levels(body.get("bids"), "bids"),
        asks=_levels(body.get("asks"), "asks"),
        source=source,
        timestamp=timestamp or fetched_at,
    )


def _levels(raw: Any, field: str) -> list[OrderBookLevel]:
    if not isinstance(raw, Sequence) or isinstance(raw, str | bytes):
        raise InvalidProviderResponseError(
            f"order book {field!r} must be a list, got {type(raw).__name__}"
        )
    levels: list[OrderBookLevel] = []
    for index, level in enumerate(raw):
        if not isinstance(level, Sequence) or isinstance(level, str | bytes) or len(level) < 2:
            raise InvalidProviderResponseError(
                f"order book {field!r} row {index} must be a [price, quantity] pair"
            )
        levels.append(
            build(
                OrderBookLevel,
                f"order book {field!r} row {index}",
                price=to_decimal(level[0], f"order book {field!r} row {index} price"),
                quantity=to_decimal(level[1], f"order book {field!r} row {index} quantity"),
            )
        )
    return levels


__all__ = [
    "extract_funding_interval_hours",
    "map_funding_rate",
    "map_open_interest",
    "map_order_book_snapshot",
    "map_taker_flow",
    "normalize_symbol",
    "to_futures_interval",
]
