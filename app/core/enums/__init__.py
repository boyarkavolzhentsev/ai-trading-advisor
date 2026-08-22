"""Strongly typed enums shared across the whole system."""

from __future__ import annotations

from app.core.enums.instrument import InstrumentStatus
from app.core.enums.judge import JudgeVerdictType
from app.core.enums.market import MarketType, Timeframe
from app.core.enums.regime import MarketRegime
from app.core.enums.session import TradingSessionStatus
from app.core.enums.trade import TradeDirection, TradeStatus

__all__ = [
    "InstrumentStatus",
    "JudgeVerdictType",
    "MarketRegime",
    "MarketType",
    "Timeframe",
    "TradeDirection",
    "TradeStatus",
    "TradingSessionStatus",
]
