"""Shared builders for Stage 2B flow-analyst tests.

Builds realistic ``FlowFeatureSnapshot`` fixtures by feeding raw events
through the real Stage 2A ``FlowFeatureEngine`` and calculators rather than
hand-constructing internal feature blocks - so fixtures carry genuine
Stage 2A quality semantics (VALID/PARTIAL/STALE/UNAVAILABLE) instead of a
fabricated approximation of them. Not a test module itself (no ``test_``
prefix): pytest will not collect it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.core.enums.instrument import ContractType
from app.core.enums.order import OrderSide
from app.core.models.analytics_window import AnalyticsWindow
from app.core.models.funding import FundingRate
from app.core.models.liquidation import LiquidationEvent
from app.core.models.open_interest import OpenInterest
from app.core.models.order_book import OrderBookLevel, OrderBookSnapshot
from app.core.models.order_book_features import DepthBand
from app.core.models.trade_event import TradeEvent
from app.flow.engine import FlowFeatureEngine

NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)

WINDOW_10S = AnalyticsWindow(label="10s", duration=timedelta(seconds=10))
WINDOW_1M = AnalyticsWindow(label="1m", duration=timedelta(minutes=1))
WINDOWS = (WINDOW_10S, WINDOW_1M)

BANDS = (DepthBand(label="top5", top_n=5),)


def make_engine(
    *, windows: tuple[AnalyticsWindow, ...] = WINDOWS, depth_bands: tuple[DepthBand, ...] = BANDS
) -> FlowFeatureEngine:
    return FlowFeatureEngine(windows=windows, depth_bands=depth_bands)


def build_snapshot(engine: FlowFeatureEngine, *, symbol: str = "BTCUSDT", contract_type=ContractType.PERPETUAL, observation_time=NOW):
    return engine.build_snapshot(
        symbol=symbol, contract_type=contract_type, observation_time=observation_time, default_source="test"
    )


def trade(
    symbol: str = "BTCUSDT",
    *,
    seconds_ago: float,
    side: OrderSide,
    price: str,
    quantity: str,
    trade_id: int,
    contract_type: ContractType = ContractType.PERPETUAL,
) -> TradeEvent:
    return TradeEvent(
        symbol=symbol,
        contract_type=contract_type,
        trade_id=trade_id,
        price=Decimal(price),
        quantity=Decimal(quantity),
        side=side,
        timestamp=NOW - timedelta(seconds=seconds_ago),
        source="test:trade",
    )


def liquidation(
    symbol: str = "BTCUSDT",
    *,
    seconds_ago: float,
    side: OrderSide,
    price: str = "100",
    quantity: str,
    contract_type: ContractType = ContractType.PERPETUAL,
) -> LiquidationEvent:
    return LiquidationEvent(
        symbol=symbol,
        contract_type=contract_type,
        side=side,
        price=Decimal(price),
        quantity=Decimal(quantity),
        timestamp=NOW - timedelta(seconds=seconds_ago),
        source="test:liquidation",
    )


def order_book_snapshot(
    symbol: str = "BTCUSDT",
    *,
    seconds_ago: float = 0,
    bids: list[tuple[str, str]],
    asks: list[tuple[str, str]],
    update_id: int = 1,
    contract_type: ContractType = ContractType.PERPETUAL,
) -> OrderBookSnapshot:
    return OrderBookSnapshot(
        symbol=symbol,
        contract_type=contract_type,
        last_update_id=update_id,
        bids=[OrderBookLevel(price=Decimal(p), quantity=Decimal(q)) for p, q in bids],
        asks=[OrderBookLevel(price=Decimal(p), quantity=Decimal(q)) for p, q in asks],
        source="test:order_book",
        timestamp=NOW - timedelta(seconds=seconds_ago),
    )


def open_interest(
    symbol: str = "BTCUSDT",
    *,
    seconds_ago: float,
    value: str,
    contract_type: ContractType = ContractType.PERPETUAL,
) -> OpenInterest:
    return OpenInterest(
        symbol=symbol,
        contract_type=contract_type,
        open_interest=Decimal(value),
        source="test:open_interest",
        timestamp=NOW - timedelta(seconds=seconds_ago),
    )


def funding_rate(
    symbol: str = "BTCUSDT",
    *,
    seconds_ago: float,
    rate: str,
    mark_price: str = "100",
    index_price: str = "100",
    contract_type: ContractType = ContractType.PERPETUAL,
) -> FundingRate:
    return FundingRate(
        symbol=symbol,
        contract_type=contract_type,
        funding_rate=Decimal(rate),
        mark_price=Decimal(mark_price),
        index_price=Decimal(index_price),
        source="test:funding",
        timestamp=NOW - timedelta(seconds=seconds_ago),
    )
