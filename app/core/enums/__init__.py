"""Strongly typed enums shared across the whole system."""

from __future__ import annotations

from app.core.enums.instrument import ContractType, InstrumentStatus
from app.core.enums.judge import JudgeVerdictType
from app.core.enums.market import MarketType, Timeframe
from app.core.enums.order import OrderSide
from app.core.enums.quality import FeatureQuality
from app.core.enums.regime import MarketRegime
from app.core.enums.session import TradingSessionStatus
from app.core.enums.stream import StreamStatus
from app.core.enums.trade import TradeDirection, TradeStatus

__all__ = [
    "ContractType",
    "FeatureQuality",
    "InstrumentStatus",
    "JudgeVerdictType",
    "MarketRegime",
    "MarketType",
    "OrderSide",
    "StreamStatus",
    "Timeframe",
    "TradeDirection",
    "TradeStatus",
    "TradingSessionStatus",
]
