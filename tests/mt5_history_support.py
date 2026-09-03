"""Shared fixtures for Stage 10D deal-history tests.

Not a test module itself (no ``test_`` prefix): pytest will not collect it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

from app.core.enums.mt5_history import MT5DealEntry, MT5DealType
from app.core.models.mt5_history import MT5Deal

__all__ = [
    "NOW",
    "WINDOW_END",
    "WINDOW_START",
    "default_deal",
    "default_raw_deal",
]

NOW = datetime(2026, 1, 2, 12, 0, 0, tzinfo=UTC)
WINDOW_START = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
WINDOW_END = datetime(2026, 1, 2, 0, 0, 0, tzinfo=UTC)


def default_deal(**overrides: object) -> MT5Deal:
    fields: dict[str, object] = {
        "ticket": 5001,
        "order": 4001,
        "position_id": 3001,
        "time": WINDOW_START,
        "symbol": "EURUSD",
        "deal_type": MT5DealType.BUY,
        "entry": MT5DealEntry.OUT,
        "volume": Decimal("1"),
        "price": Decimal("100"),
        "profit": Decimal("0"),
        "commission": Decimal("0"),
        "swap": Decimal("0"),
        "fee": Decimal("0"),
    }
    fields.update(overrides)
    return MT5Deal(**fields)


def default_raw_deal(
    *,
    ticket: int = 5001,
    order: int = 4001,
    position_id: int = 3001,
    time_msc: int = int(WINDOW_START.timestamp() * 1000),
    symbol: str = "EURUSD",
    type: int = 0,
    entry: int = 1,
    volume: float = 1.0,
    price: float = 100.0,
    profit: float = 0.0,
    commission: float = 0.0,
    swap: float = 0.0,
    fee: float = 0.0,
) -> SimpleNamespace:
    return SimpleNamespace(
        ticket=ticket,
        order=order,
        position_id=position_id,
        time_msc=time_msc,
        symbol=symbol,
        type=type,
        entry=entry,
        volume=volume,
        price=price,
        profit=profit,
        commission=commission,
        swap=swap,
        fee=fee,
    )
