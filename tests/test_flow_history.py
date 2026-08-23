"""Tests for app.flow.history: bounded history, eviction, dropped-count."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.core.enums.instrument import ContractType
from app.core.enums.order import OrderSide
from app.core.models.trade_event import TradeEvent
from app.flow.history import FeatureHistoryStore, SymbolFeatureHistory


def _trade(trade_id: int) -> TradeEvent:
    return TradeEvent(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        trade_id=trade_id,
        price=Decimal("100"),
        quantity=Decimal("1"),
        side=OrderSide.BUY,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        source="test:trade",
    )


def test_with_capacity_builds_independent_bounded_buffers() -> None:
    history = SymbolFeatureHistory.with_capacity(raw_capacity=3)
    assert history.trades.maxlen == 3
    assert history.liquidations.maxlen == 3
    assert history.trades.dropped_count == 0


def test_eviction_and_dropped_count() -> None:
    history = SymbolFeatureHistory.with_capacity(raw_capacity=2)
    for i in range(5):
        history.trades.append(_trade(i))
    assert len(history.trades) == 2
    assert history.trades.dropped_count == 3
    remaining_ids = [t.trade_id for t in history.trades.latest()]
    assert remaining_ids == [3, 4]  # oldest evicted, newest retained


def test_buffers_satisfy_feature_history_store_protocol() -> None:
    history = SymbolFeatureHistory.with_capacity()
    assert isinstance(history.trades, FeatureHistoryStore)
    assert isinstance(history.liquidations, FeatureHistoryStore)
    assert isinstance(history.order_book, FeatureHistoryStore)
    assert isinstance(history.open_interest, FeatureHistoryStore)
    assert isinstance(history.funding, FeatureHistoryStore)
    assert isinstance(history.snapshots, FeatureHistoryStore)


def test_capacities_are_configurable_and_independent() -> None:
    history = SymbolFeatureHistory.with_capacity(
        raw_capacity=10, order_book_capacity=1, open_interest_capacity=2, funding_capacity=3, snapshot_capacity=4
    )
    assert history.trades.maxlen == 10
    assert history.order_book.maxlen == 1
    assert history.open_interest.maxlen == 2
    assert history.funding.maxlen == 3
    assert history.snapshots.maxlen == 4
