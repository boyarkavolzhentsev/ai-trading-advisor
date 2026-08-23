"""Contract rules for the Stage 1B futures/perpetual domain models."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.enums.instrument import ContractType
from app.core.enums.market import Timeframe
from app.core.enums.order import OrderSide
from app.core.models.funding import FundingRate
from app.core.models.liquidation import LiquidationEvent
from app.core.models.open_interest import OpenInterest
from app.core.models.order_book import OrderBookLevel, OrderBookSnapshot
from app.core.models.taker_flow import TakerFlowSnapshot


def _funding_rate(now: datetime, **overrides: object) -> FundingRate:
    fields: dict[str, object] = {
        "symbol": "BTCUSDT",
        "contract_type": ContractType.PERPETUAL,
        "funding_rate": Decimal("-0.00010000"),
        "mark_price": Decimal("64100.5"),
        "index_price": Decimal("64099.1"),
        "source": "binance_futures:funding_rate",
        "timestamp": now,
    }
    fields.update(overrides)
    return FundingRate(**fields)


def _taker_flow(now: datetime, **overrides: object) -> TakerFlowSnapshot:
    fields: dict[str, object] = {
        "symbol": "BTCUSDT",
        "contract_type": ContractType.PERPETUAL,
        "timeframe": Timeframe.M5,
        "timestamp": now,
        "buy_volume": Decimal("7.5"),
        "sell_volume": Decimal("5.0"),
        "source": "binance_futures:taker_flow",
    }
    fields.update(overrides)
    return TakerFlowSnapshot(**fields)


def _order_book(now: datetime, **overrides: object) -> OrderBookSnapshot:
    fields: dict[str, object] = {
        "symbol": "BTCUSDT",
        "contract_type": ContractType.PERPETUAL,
        "last_update_id": 1,
        "bids": [OrderBookLevel(price=Decimal("100"), quantity=Decimal("1"))],
        "asks": [OrderBookLevel(price=Decimal("101"), quantity=Decimal("1"))],
        "source": "binance_futures:order_book",
        "timestamp": now,
    }
    fields.update(overrides)
    return OrderBookSnapshot(**fields)


# --------------------------------------------------------------------------- #
# ContractType / OrderSide
# --------------------------------------------------------------------------- #


def test_contract_type_members() -> None:
    assert {member.value for member in ContractType} == {"SPOT", "PERPETUAL"}


def test_order_side_members() -> None:
    assert {member.value for member in OrderSide} == {"BUY", "SELL"}


def test_perpetual_funding_rate_is_not_spot(now: datetime) -> None:
    funding = _funding_rate(now, contract_type=ContractType.PERPETUAL)
    assert funding.contract_type is not ContractType.SPOT
    assert funding.symbol == "BTCUSDT"


# --------------------------------------------------------------------------- #
# FundingRate
# --------------------------------------------------------------------------- #


def test_funding_rate_allows_negative_rate(now: datetime) -> None:
    funding = _funding_rate(now, funding_rate=Decimal("-0.05"))
    assert funding.funding_rate == Decimal("-0.05")


def test_funding_rate_interval_defaults_to_none(now: datetime) -> None:
    assert _funding_rate(now).funding_interval_hours is None


def test_funding_rate_interval_does_not_default_to_eight_hours(now: datetime) -> None:
    """Regression guard for the explicit "do not hard-code 8h" decision."""
    assert _funding_rate(now).funding_interval_hours != 8


def test_funding_rate_rejects_non_positive_interval(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _funding_rate(now, funding_interval_hours=0)


def test_funding_rate_rejects_negative_mark_price(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _funding_rate(now, mark_price=Decimal("-1"))


def test_funding_rate_is_immutable(now: datetime) -> None:
    funding = _funding_rate(now)
    with pytest.raises(ValidationError):
        funding.funding_rate = Decimal("0")


# --------------------------------------------------------------------------- #
# OpenInterest
# --------------------------------------------------------------------------- #


def test_open_interest_rejects_negative_value(now: datetime) -> None:
    with pytest.raises(ValidationError):
        OpenInterest(
            symbol="BTCUSDT",
            contract_type=ContractType.PERPETUAL,
            open_interest=Decimal("-1"),
            source="binance_futures:open_interest",
            timestamp=now,
        )


def test_open_interest_accepts_zero(now: datetime) -> None:
    open_interest = OpenInterest(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        open_interest=Decimal("0"),
        source="binance_futures:open_interest",
        timestamp=now,
    )
    assert open_interest.open_interest == Decimal("0")


# --------------------------------------------------------------------------- #
# TakerFlowSnapshot
# --------------------------------------------------------------------------- #


def test_taker_flow_total_volume_is_sum(now: datetime) -> None:
    snapshot = _taker_flow(now, buy_volume=Decimal("7"), sell_volume=Decimal("3"))
    assert snapshot.total_volume == Decimal("10")


def test_taker_flow_delta_is_buy_minus_sell(now: datetime) -> None:
    snapshot = _taker_flow(now, buy_volume=Decimal("7"), sell_volume=Decimal("3"))
    assert snapshot.delta == Decimal("4")


def test_taker_flow_delta_can_be_negative(now: datetime) -> None:
    snapshot = _taker_flow(now, buy_volume=Decimal("2"), sell_volume=Decimal("9"))
    assert snapshot.delta == Decimal("-7")


def test_taker_flow_buy_ratio(now: datetime) -> None:
    snapshot = _taker_flow(now, buy_volume=Decimal("3"), sell_volume=Decimal("1"))
    assert snapshot.buy_ratio == pytest.approx(0.75)


def test_taker_flow_buy_ratio_is_zero_for_no_volume(now: datetime) -> None:
    snapshot = _taker_flow(now, buy_volume=Decimal("0"), sell_volume=Decimal("0"))
    assert snapshot.buy_ratio == 0.0


def test_taker_flow_buy_quote_volume_is_optional(now: datetime) -> None:
    assert _taker_flow(now).buy_quote_volume is None


def test_taker_flow_rejects_negative_buy_volume(now: datetime) -> None:
    with pytest.raises(ValidationError):
        _taker_flow(now, buy_volume=Decimal("-1"))


def test_taker_flow_model_has_no_interpretation_fields(now: datetime) -> None:
    """Guard against reintroducing signal/pressure fields onto this contract."""
    fields = set(TakerFlowSnapshot.model_fields)
    assert fields == {
        "symbol",
        "contract_type",
        "timeframe",
        "timestamp",
        "buy_volume",
        "sell_volume",
        "buy_quote_volume",
        "source",
    }


# --------------------------------------------------------------------------- #
# OrderBookSnapshot
# --------------------------------------------------------------------------- #


def test_order_book_allows_empty_sides(now: datetime) -> None:
    snapshot = _order_book(now, bids=[], asks=[])
    assert snapshot.bids == []
    assert snapshot.asks == []


def test_order_book_rejects_crossed_book(now: datetime) -> None:
    with pytest.raises(ValidationError, match="best ask must not be below best bid"):
        _order_book(
            now,
            bids=[OrderBookLevel(price=Decimal("101"), quantity=Decimal("1"))],
            asks=[OrderBookLevel(price=Decimal("100"), quantity=Decimal("1"))],
        )


def test_order_book_allows_touching_book(now: datetime) -> None:
    snapshot = _order_book(
        now,
        bids=[OrderBookLevel(price=Decimal("100"), quantity=Decimal("1"))],
        asks=[OrderBookLevel(price=Decimal("100"), quantity=Decimal("1"))],
    )
    assert snapshot.bids[0].price == snapshot.asks[0].price


def test_order_book_rejects_negative_level_price() -> None:
    with pytest.raises(ValidationError):
        OrderBookLevel(price=Decimal("-1"), quantity=Decimal("1"))


def test_order_book_model_has_no_imbalance_fields(now: datetime) -> None:
    """Guard against reintroducing order-book pressure/imbalance calculation."""
    fields = set(OrderBookSnapshot.model_fields)
    assert fields == {
        "symbol",
        "contract_type",
        "last_update_id",
        "bids",
        "asks",
        "source",
        "timestamp",
    }


# --------------------------------------------------------------------------- #
# LiquidationEvent
# --------------------------------------------------------------------------- #


def test_liquidation_event_holds_raw_order_side(now: datetime) -> None:
    event = LiquidationEvent(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        side=OrderSide.SELL,
        price=Decimal("64000"),
        quantity=Decimal("0.5"),
        timestamp=now,
        source="binance_futures:liquidation",
    )
    assert event.side is OrderSide.SELL
    assert event.contract_type is ContractType.PERPETUAL


def test_liquidation_event_rejects_string_direction_value(now: datetime) -> None:
    with pytest.raises(ValidationError):
        LiquidationEvent(
            symbol="BTCUSDT",
            contract_type=ContractType.PERPETUAL,
            side="LONG",  # not a raw order side
            price=Decimal("64000"),
            quantity=Decimal("0.5"),
            timestamp=now,
            source="binance_futures:liquidation",
        )


def test_liquidation_event_rejects_negative_quantity(now: datetime) -> None:
    with pytest.raises(ValidationError):
        LiquidationEvent(
            symbol="BTCUSDT",
            contract_type=ContractType.PERPETUAL,
            side=OrderSide.BUY,
            price=Decimal("64000"),
            quantity=Decimal("-1"),
            timestamp=now,
            source="binance_futures:liquidation",
        )
