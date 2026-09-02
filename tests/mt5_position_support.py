"""Shared fakes for Stage 10C position/symbol/sizing tests.

Not a test module itself (no ``test_`` prefix): pytest will not collect it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

from app.core.enums.mt5_symbol import MT5SymbolTradeMode
from app.core.enums.order import OrderSide
from app.core.models.mt5_position import MT5Position
from app.core.models.mt5_symbol import MT5SymbolFacts

__all__ = [
    "NOW",
    "default_position",
    "default_raw_position",
    "default_raw_symbol_info",
    "default_raw_tick",
    "default_symbol_facts",
]

NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


def default_position(**overrides: object) -> MT5Position:
    fields: dict[str, object] = {
        "as_of": NOW,
        "ticket": 1001,
        "symbol": "EURUSD",
        "side": OrderSide.BUY,
        "volume": Decimal("1"),
        "price_open": Decimal("100"),
        "price_current": Decimal("100"),
        "stop_loss": Decimal("95"),
    }
    fields.update(overrides)
    return MT5Position(**fields)


def default_symbol_facts(**overrides: object) -> MT5SymbolFacts:
    fields: dict[str, object] = {
        "as_of": NOW,
        "symbol": "EURUSD",
        "trade_tick_size": Decimal("0.00001"),
        "trade_tick_value_loss": Decimal("1"),
        "volume_min": Decimal("0.01"),
        "volume_max": Decimal("100"),
        "volume_step": Decimal("0.01"),
        "trade_stops_level": 0,
        "trade_mode": MT5SymbolTradeMode.FULL,
        "bid": Decimal("100"),
        "ask": Decimal("100.001"),
    }
    fields.update(overrides)
    return MT5SymbolFacts(**fields)


def default_raw_position(
    *,
    ticket: int = 1001,
    symbol: str = "EURUSD",
    type: int = 0,
    volume: float = 1.0,
    price_open: float = 100.0,
    price_current: float = 100.0,
    sl: float = 95.0,
) -> SimpleNamespace:
    return SimpleNamespace(
        ticket=ticket,
        symbol=symbol,
        type=type,
        volume=volume,
        price_open=price_open,
        price_current=price_current,
        sl=sl,
    )


def default_raw_symbol_info(
    *,
    trade_tick_size: float = 0.00001,
    trade_tick_value_loss: float = 1.0,
    volume_min: float = 0.01,
    volume_max: float = 100.0,
    volume_step: float = 0.01,
    trade_stops_level: int = 0,
    trade_mode: int = 4,
) -> SimpleNamespace:
    return SimpleNamespace(
        trade_tick_size=trade_tick_size,
        trade_tick_value_loss=trade_tick_value_loss,
        volume_min=volume_min,
        volume_max=volume_max,
        volume_step=volume_step,
        trade_stops_level=trade_stops_level,
        trade_mode=trade_mode,
    )


def default_raw_tick(*, bid: float = 100.0, ask: float = 100.001) -> SimpleNamespace:
    return SimpleNamespace(bid=bid, ask=ask)
