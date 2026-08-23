"""Binance USD-M futures real-time payload -> internal contract normalization.

Pure functions only, mirroring the REST futures mapper's posture: no
network, no state, no decisions. Anything that does not fit the expected
shape raises ``InvalidProviderResponseError`` instead of being guessed at or
repaired. Reuses ``app.market_data.parsing`` exactly like the REST mapper.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.core.enums.instrument import ContractType
from app.core.enums.order import OrderSide
from app.core.models.funding import FundingRate
from app.core.models.liquidation import LiquidationEvent
from app.core.models.order_book import OrderBookDeltaEvent, OrderBookLevel
from app.core.models.trade_event import TradeEvent
from app.market_data.exceptions import InvalidProviderResponseError
from app.market_data.parsing import (
    as_decimal,
    as_mapping,
    as_str,
    build,
    optional_timestamp_from_millis,
    timestamp_from_millis,
    to_decimal,
)


def map_agg_trade(payload: Any, *, source: str) -> TradeEvent:
    """Map an ``aggTrade`` event onto ``TradeEvent``.

    ``m`` (isBuyerMaker) is transcribed directly: ``m=True`` means the buyer
    was the maker, so the trade was taker-initiated on the SELL side;
    ``m=False`` means the buyer was the taker, so the trade was
    taker-initiated BUY. This reads the exchange's own flag; it is never an
    inference.
    """
    body = as_mapping(payload, "agg trade")
    price = as_decimal(body, "p", "agg trade")
    quantity = as_decimal(body, "q", "agg trade")
    is_buyer_maker = body.get("m")
    if not isinstance(is_buyer_maker, bool):
        raise InvalidProviderResponseError("agg trade has no usable 'm' field")
    side = OrderSide.SELL if is_buyer_maker else OrderSide.BUY

    return build(
        TradeEvent,
        "agg trade",
        symbol=as_str(body, "s", "agg trade"),
        contract_type=ContractType.PERPETUAL,
        trade_id=_as_int(body, "a", "agg trade"),
        price=price,
        quantity=quantity,
        quote_quantity=price * quantity,
        side=side,
        first_trade_id=_as_optional_int(body, "f"),
        last_trade_id=_as_optional_int(body, "l"),
        timestamp=timestamp_from_millis(_required(body, "T", "agg trade"), "agg trade trade time"),
        source=source,
    )


def map_mark_price(payload: Any, *, funding_interval_hours: int | None, source: str) -> FundingRate:
    """Map a ``markPriceUpdate`` event onto ``FundingRate``.

    The stream never discloses the funding interval; callers supply the last
    known value from the REST ``fundingInfo`` side-channel (possibly
    ``None``) - it is never hard-coded here.
    """
    body = as_mapping(payload, "mark price")
    return build(
        FundingRate,
        "mark price",
        symbol=as_str(body, "s", "mark price"),
        contract_type=ContractType.PERPETUAL,
        funding_rate=as_decimal(body, "r", "mark price"),
        funding_interval_hours=funding_interval_hours,
        mark_price=as_decimal(body, "p", "mark price"),
        index_price=as_decimal(body, "i", "mark price"),
        next_funding_time=optional_timestamp_from_millis(
            body.get("T"), "mark price next funding time"
        ),
        source=source,
        timestamp=timestamp_from_millis(_required(body, "E", "mark price"), "mark price event time"),
    )


def map_liquidation(payload: Any, *, source: str) -> LiquidationEvent:
    """Map a ``forceOrder`` event's nested order object onto ``LiquidationEvent``.

    Uses the average fill price (``ap``) when it is nonzero, else the
    order's limit price (``p``) as a fallback - ``ap`` reflects what
    actually happened, ``p`` covers the rare case a liquidation order
    hasn't filled yet.
    """
    body = as_mapping(payload, "liquidation")
    order = as_mapping(body.get("o"), "liquidation order")
    side_raw = order.get("S")
    if side_raw not in ("BUY", "SELL"):
        raise InvalidProviderResponseError(f"liquidation order has invalid side: {side_raw!r}")

    avg_price = as_decimal(order, "ap", "liquidation order")
    price = avg_price if avg_price != 0 else as_decimal(order, "p", "liquidation order")

    return build(
        LiquidationEvent,
        "liquidation",
        symbol=as_str(order, "s", "liquidation order"),
        contract_type=ContractType.PERPETUAL,
        side=OrderSide(side_raw),
        price=price,
        quantity=as_decimal(order, "q", "liquidation order"),
        timestamp=timestamp_from_millis(
            _required(order, "T", "liquidation order"), "liquidation order trade time"
        ),
        source=source,
    )


def map_depth_update(payload: Any, *, source: str) -> OrderBookDeltaEvent:
    """Map a ``depthUpdate`` event onto ``OrderBookDeltaEvent``."""
    body = as_mapping(payload, "depth update")
    return build(
        OrderBookDeltaEvent,
        "depth update",
        symbol=as_str(body, "s", "depth update"),
        contract_type=ContractType.PERPETUAL,
        first_update_id=_as_int(body, "U", "depth update"),
        final_update_id=_as_int(body, "u", "depth update"),
        previous_final_update_id=_as_int(body, "pu", "depth update"),
        bid_updates=_levels(body.get("b"), "b"),
        ask_updates=_levels(body.get("a"), "a"),
        event_time=timestamp_from_millis(_required(body, "E", "depth update"), "depth update event time"),
        transaction_time=optional_timestamp_from_millis(
            body.get("T"), "depth update transaction time"
        ),
        source=source,
    )


def _levels(raw: Any, field: str) -> list[OrderBookLevel]:
    if not isinstance(raw, list):
        raise InvalidProviderResponseError(
            f"depth update {field!r} must be a list, got {type(raw).__name__}"
        )
    levels: list[OrderBookLevel] = []
    for index, level in enumerate(raw):
        if not isinstance(level, list) or len(level) < 2:
            raise InvalidProviderResponseError(
                f"depth update {field!r} row {index} must be a [price, quantity] pair"
            )
        levels.append(
            build(
                OrderBookLevel,
                f"depth update {field!r} row {index}",
                price=to_decimal(level[0], f"depth update {field!r} row {index} price"),
                quantity=to_decimal(level[1], f"depth update {field!r} row {index} quantity"),
            )
        )
    return levels


def _as_int(body: Mapping[str, Any], key: str, context: str) -> int:
    value = body.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidProviderResponseError(
            f"{context} field {key!r} must be an integer, got {type(value).__name__}"
        )
    return value


def _as_optional_int(body: Mapping[str, Any], key: str) -> int | None:
    value = body.get(key)
    if value is None or isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _required(body: Mapping[str, Any], key: str, context: str) -> Any:
    if key not in body:
        raise InvalidProviderResponseError(f"{context} is missing field {key!r}")
    return body[key]


__all__ = ["map_agg_trade", "map_depth_update", "map_liquidation", "map_mark_price"]
