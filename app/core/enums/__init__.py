"""Strongly typed enums shared across the whole system."""

from __future__ import annotations

from app.core.enums.flow_analysis import (
    AgreementVerdict,
    AnalysisDimension,
    AnalystOutcome,
    AnalystType,
    BasisSign,
    CorrelationRelationship,
    DepthTrend,
    FundingSign,
    FundingTrend,
    LiquidationActivity,
    LiquidationPressure,
    OpenInterestTrend,
    OrdinalTrend,
    OrderBookPressure,
    PriceFlowRelationship,
    TakerFlowPressure,
)
from app.core.enums.economic_calendar import (
    CentralBank,
    EconomicCategory,
    EconomicEventImportance,
    EconomicEventStatus,
)
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
    "AgreementVerdict",
    "AnalysisDimension",
    "AnalystOutcome",
    "AnalystType",
    "BasisSign",
    "CentralBank",
    "ContractType",
    "CorrelationRelationship",
    "DepthTrend",
    "EconomicCategory",
    "EconomicEventImportance",
    "EconomicEventStatus",
    "FeatureQuality",
    "FundingSign",
    "FundingTrend",
    "InstrumentStatus",
    "JudgeVerdictType",
    "LiquidationActivity",
    "LiquidationPressure",
    "MarketRegime",
    "MarketType",
    "OpenInterestTrend",
    "OrderBookPressure",
    "OrderSide",
    "OrdinalTrend",
    "PriceFlowRelationship",
    "StreamStatus",
    "TakerFlowPressure",
    "Timeframe",
    "TradeDirection",
    "TradeStatus",
    "TradingSessionStatus",
]
