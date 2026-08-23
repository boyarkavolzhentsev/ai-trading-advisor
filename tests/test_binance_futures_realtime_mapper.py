"""Binance USD-M futures real-time payload normalization.

All payloads here are hand-written synthetic shapes copied from the public
API documentation, not recorded market data.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.core.enums.instrument import ContractType
from app.core.enums.order import OrderSide
from app.market_data.exceptions import InvalidProviderResponseError
from app.market_data.providers.binance.futures.realtime import mapper

SOURCE = "binance_futures:test"
NOW = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)


def _millis(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)


# --------------------------------------------------------------------------- #
# aggTrade / maker-taker mapping
# --------------------------------------------------------------------------- #


def _agg_trade(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "e": "aggTrade",
        "E": _millis(NOW),
        "s": "BTCUSDT",
        "a": 5933014,
        "p": "64100.50",
        "q": "0.500",
        "f": 100,
        "l": 105,
        "T": _millis(NOW),
        "m": True,
    }
    body.update(overrides)
    return body


def test_map_agg_trade_buyer_is_maker_means_taker_sell() -> None:
    trade = mapper.map_agg_trade(_agg_trade(m=True), source=SOURCE)
    assert trade.side is OrderSide.SELL


def test_map_agg_trade_buyer_is_taker_means_taker_buy() -> None:
    trade = mapper.map_agg_trade(_agg_trade(m=False), source=SOURCE)
    assert trade.side is OrderSide.BUY


def test_map_agg_trade_fields() -> None:
    trade = mapper.map_agg_trade(_agg_trade(), source=SOURCE)
    assert trade.symbol == "BTCUSDT"
    assert trade.contract_type is ContractType.PERPETUAL
    assert trade.trade_id == 5933014
    assert trade.price == Decimal("64100.50")
    assert trade.quantity == Decimal("0.500")
    assert trade.quote_quantity == Decimal("64100.50") * Decimal("0.500")
    assert trade.first_trade_id == 100
    assert trade.last_trade_id == 105
    assert trade.timestamp == NOW
    assert trade.source == SOURCE


def test_map_agg_trade_rejects_missing_m_field() -> None:
    payload = _agg_trade()
    del payload["m"]
    with pytest.raises(InvalidProviderResponseError, match="'m' field"):
        mapper.map_agg_trade(payload, source=SOURCE)


def test_map_agg_trade_rejects_non_boolean_m() -> None:
    with pytest.raises(InvalidProviderResponseError, match="'m' field"):
        mapper.map_agg_trade(_agg_trade(m="true"), source=SOURCE)


def test_map_agg_trade_rejects_missing_price() -> None:
    payload = _agg_trade()
    del payload["p"]
    with pytest.raises(InvalidProviderResponseError, match="missing field 'p'"):
        mapper.map_agg_trade(payload, source=SOURCE)


def test_map_agg_trade_tolerates_missing_optional_trade_id_range() -> None:
    payload = _agg_trade()
    del payload["f"]
    del payload["l"]
    trade = mapper.map_agg_trade(payload, source=SOURCE)
    assert trade.first_trade_id is None
    assert trade.last_trade_id is None


# --------------------------------------------------------------------------- #
# mark price / funding
# --------------------------------------------------------------------------- #


def _mark_price(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "e": "markPriceUpdate",
        "E": _millis(NOW),
        "s": "BTCUSDT",
        "p": "64100.50000000",
        "i": "64099.10000000",
        "P": "64098.00000000",
        "r": "0.00010000",
        "T": _millis(NOW),
    }
    body.update(overrides)
    return body


def test_map_mark_price_fields() -> None:
    funding = mapper.map_mark_price(_mark_price(), funding_interval_hours=8, source=SOURCE)
    assert funding.symbol == "BTCUSDT"
    assert funding.contract_type is ContractType.PERPETUAL
    assert funding.funding_rate == Decimal("0.00010000")
    assert funding.funding_interval_hours == 8
    assert funding.mark_price == Decimal("64100.50000000")
    assert funding.index_price == Decimal("64099.10000000")
    assert funding.next_funding_time == NOW
    assert funding.timestamp == NOW
    assert funding.source == SOURCE


def test_map_mark_price_allows_negative_funding_rate() -> None:
    funding = mapper.map_mark_price(
        _mark_price(r="-0.00050000"), funding_interval_hours=None, source=SOURCE
    )
    assert funding.funding_rate == Decimal("-0.00050000")


def test_map_mark_price_interval_defaults_to_none_never_eight() -> None:
    funding = mapper.map_mark_price(_mark_price(), funding_interval_hours=None, source=SOURCE)
    assert funding.funding_interval_hours is None


def test_map_mark_price_zero_next_funding_time_is_none() -> None:
    funding = mapper.map_mark_price(_mark_price(T=0), funding_interval_hours=None, source=SOURCE)
    assert funding.next_funding_time is None


def test_map_mark_price_rejects_missing_mark_price() -> None:
    payload = _mark_price()
    del payload["p"]
    with pytest.raises(InvalidProviderResponseError, match="missing field 'p'"):
        mapper.map_mark_price(payload, funding_interval_hours=None, source=SOURCE)


# --------------------------------------------------------------------------- #
# liquidations
# --------------------------------------------------------------------------- #


def _force_order(**order_overrides: object) -> dict[str, object]:
    order: dict[str, object] = {
        "s": "BTCUSDT",
        "S": "SELL",
        "o": "LIMIT",
        "f": "IOC",
        "q": "0.500",
        "p": "64000.00",
        "ap": "63990.00",
        "X": "FILLED",
        "l": "0.500",
        "z": "0.500",
        "T": _millis(NOW),
    }
    order.update(order_overrides)
    return {"e": "forceOrder", "E": _millis(NOW), "o": order}


def test_map_liquidation_fields() -> None:
    event = mapper.map_liquidation(_force_order(), source=SOURCE)
    assert event.symbol == "BTCUSDT"
    assert event.contract_type is ContractType.PERPETUAL
    assert event.side is OrderSide.SELL
    assert event.price == Decimal("63990.00")  # average price preferred over limit price
    assert event.quantity == Decimal("0.500")
    assert event.timestamp == NOW
    assert event.source == SOURCE


def test_map_liquidation_buy_side() -> None:
    event = mapper.map_liquidation(_force_order(S="BUY"), source=SOURCE)
    assert event.side is OrderSide.BUY


def test_map_liquidation_falls_back_to_limit_price_when_average_is_zero() -> None:
    event = mapper.map_liquidation(_force_order(ap="0"), source=SOURCE)
    assert event.price == Decimal("64000.00")


def test_map_liquidation_rejects_invalid_side() -> None:
    with pytest.raises(InvalidProviderResponseError, match="invalid side"):
        mapper.map_liquidation(_force_order(S="LONG"), source=SOURCE)


def test_map_liquidation_rejects_missing_order_object() -> None:
    with pytest.raises(InvalidProviderResponseError, match="must be an object"):
        mapper.map_liquidation({"e": "forceOrder", "E": _millis(NOW)}, source=SOURCE)


# --------------------------------------------------------------------------- #
# depth updates
# --------------------------------------------------------------------------- #


def _depth_update(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "e": "depthUpdate",
        "E": _millis(NOW),
        "T": _millis(NOW),
        "s": "BTCUSDT",
        "U": 101,
        "u": 105,
        "pu": 100,
        "b": [["99.00", "1.500"], ["98.50", "0"]],
        "a": [["101.00", "2.000"]],
    }
    body.update(overrides)
    return body


def test_map_depth_update_fields() -> None:
    delta = mapper.map_depth_update(_depth_update(), source=SOURCE)
    assert delta.symbol == "BTCUSDT"
    assert delta.contract_type is ContractType.PERPETUAL
    assert delta.first_update_id == 101
    assert delta.final_update_id == 105
    assert delta.previous_final_update_id == 100
    assert delta.bid_updates[0].price == Decimal("99.00")
    assert delta.bid_updates[1].quantity == Decimal("0")
    assert delta.ask_updates[0].price == Decimal("101.00")
    assert delta.event_time == NOW
    assert delta.transaction_time == NOW
    assert delta.source == SOURCE


def test_map_depth_update_requires_pu() -> None:
    payload = _depth_update()
    del payload["pu"]
    with pytest.raises(InvalidProviderResponseError, match="'pu'"):
        mapper.map_depth_update(payload, source=SOURCE)


def test_map_depth_update_rejects_malformed_level() -> None:
    with pytest.raises(InvalidProviderResponseError, match="price, quantity"):
        mapper.map_depth_update(_depth_update(b=[["99.00"]]), source=SOURCE)


def test_map_depth_update_rejects_non_list_bids() -> None:
    with pytest.raises(InvalidProviderResponseError, match="must be a list"):
        mapper.map_depth_update(_depth_update(b={"not": "a list"}), source=SOURCE)


def test_map_depth_update_rejects_final_below_first() -> None:
    with pytest.raises(InvalidProviderResponseError, match="violates OrderBookDeltaEvent"):
        mapper.map_depth_update(_depth_update(U=200, u=100, pu=199), source=SOURCE)
