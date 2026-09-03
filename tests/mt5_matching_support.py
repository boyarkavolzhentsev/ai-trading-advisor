"""Shared fixtures for Stage 10E matching/tracking tests.

Not a test module itself (no ``test_`` prefix): pytest will not collect it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.core.enums.market import MarketType
from app.core.enums.mt5_history import MT5DealEntry, MT5DealType
from app.core.enums.trade import TradeDirection, TradeStatus
from app.core.models.mt5_history import MT5Deal
from app.core.models.mt5_tracking import MT5TrackedRecommendation
from app.core.models.position import PositionRecord

__all__ = [
    "SIGNAL_TIME",
    "VALID_UNTIL",
    "default_candidate_deal",
    "default_position_record",
    "default_tracked_recommendation",
]

SIGNAL_TIME = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
VALID_UNTIL = SIGNAL_TIME + timedelta(minutes=5)


def default_candidate_deal(**overrides: object) -> MT5Deal:
    """A deal that satisfies every Stage 10E hard matching constraint
    against ``default_position_record()``'s facts out of the box."""
    fields: dict[str, object] = {
        "ticket": 9001,
        "order": 8001,
        "position_id": 7001,
        "time": SIGNAL_TIME + timedelta(minutes=1),
        "symbol": "EURUSD",
        "deal_type": MT5DealType.BUY,
        "entry": MT5DealEntry.IN,
        "volume": Decimal("1"),
        "price": Decimal("100"),
        "profit": Decimal("0"),
        "commission": Decimal("-2"),
        "swap": Decimal("0"),
        "fee": Decimal("0"),
    }
    fields.update(overrides)
    return MT5Deal(**fields)


def default_position_record(**overrides: object) -> PositionRecord:
    fields: dict[str, object] = {
        "trade_id": "trade-1",
        "symbol": "EURUSD",
        "market": MarketType.FX,
        "direction": TradeDirection.LONG,
        "signal_time": SIGNAL_TIME,
        "valid_until": VALID_UNTIL,
        "status": TradeStatus.PENDING,
        "planned_entry": Decimal("100"),
        "stop_loss": Decimal("95"),
    }
    fields.update(overrides)
    return PositionRecord(**fields)


def default_tracked_recommendation(**overrides: object) -> MT5TrackedRecommendation:
    fields: dict[str, object] = {
        "position_record": default_position_record(),
        "approved_broker_volume": Decimal("1"),
        "pre_existing_position_ids": (),
    }
    fields.update(overrides)
    return MT5TrackedRecommendation(**fields)
