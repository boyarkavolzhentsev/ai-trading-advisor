"""MarketSnapshot, TechnicalSnapshot, DataQuality and PerformanceSnapshot."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.enums import MarketType, Timeframe
from app.core.models import (
    DataQuality,
    MarketSnapshot,
    PerformanceSnapshot,
    TechnicalSnapshot,
)


def test_market_snapshot_carries_data_quality(
    now: datetime, data_quality: DataQuality
) -> None:
    snapshot = MarketSnapshot(
        symbol="TEST",
        market=MarketType.CRYPTO,
        timestamp=now,
        timeframe=Timeframe.M15,
        price=Decimal("100"),
        bid=Decimal("99.95"),
        ask=Decimal("100.05"),
        spread=Decimal("0.10"),
        data_quality=data_quality,
    )
    assert snapshot.data_quality.is_valid is True
    assert snapshot.data_quality.is_stale is False
    assert snapshot.data_quality.warnings == []


def test_market_snapshot_rejects_ask_below_bid(
    now: datetime, data_quality: DataQuality
) -> None:
    with pytest.raises(ValidationError, match="ask must be greater than or equal"):
        MarketSnapshot(
            symbol="TEST",
            market=MarketType.US,
            timestamp=now,
            timeframe=Timeframe.H1,
            price=Decimal("100"),
            bid=Decimal("100.10"),
            ask=Decimal("99.90"),
            data_quality=data_quality,
        )


def test_market_snapshot_rejects_negative_price(
    now: datetime, data_quality: DataQuality
) -> None:
    with pytest.raises(ValidationError):
        MarketSnapshot(
            symbol="TEST",
            market=MarketType.METALS,
            timestamp=now,
            timeframe=Timeframe.D1,
            price=Decimal("-1"),
            data_quality=data_quality,
        )


def test_market_snapshot_requires_symbol(
    now: datetime, data_quality: DataQuality
) -> None:
    with pytest.raises(ValidationError):
        MarketSnapshot(
            symbol="",
            market=MarketType.EU,
            timestamp=now,
            timeframe=Timeframe.M5,
            price=Decimal("100"),
            data_quality=data_quality,
        )


def test_technical_snapshot_is_generic_and_optional(now: datetime) -> None:
    snapshot = TechnicalSnapshot(
        symbol="TEST",
        timeframe=Timeframe.H4,
        timestamp=now,
    )
    assert snapshot.trend is None
    assert snapshot.momentum is None
    assert snapshot.volatility is None
    assert snapshot.market_structure is None
    assert snapshot.support_levels == []
    assert snapshot.resistance_levels == []


def test_technical_snapshot_rejects_negative_levels(now: datetime) -> None:
    with pytest.raises(ValidationError):
        TechnicalSnapshot(
            symbol="TEST",
            timeframe=Timeframe.H4,
            timestamp=now,
            support_levels=[Decimal("-5")],
        )


def test_performance_snapshot_defaults_to_empty_sample() -> None:
    snapshot = PerformanceSnapshot()
    assert snapshot.total_trades == 0
    assert snapshot.win_rate is None
    assert snapshot.profit_factor is None
    assert snapshot.expectancy is None
    assert snapshot.max_drawdown is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("total_trades", -1),
        ("wins", -1),
        ("win_rate", 1.5),
        ("profit_factor", -1.0),
        ("max_drawdown", Decimal("-1")),
    ],
)
def test_performance_snapshot_rejects_invalid_values(
    field: str, value: object
) -> None:
    with pytest.raises(ValidationError):
        PerformanceSnapshot(**{field: value})
