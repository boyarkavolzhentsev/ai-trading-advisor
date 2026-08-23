"""Typed domain contracts exchanged between components."""

from __future__ import annotations

from app.core.models.analytics_window import AnalyticsWindow
from app.core.models.assessment import AgentAssessment
from app.core.models.base import DomainModel, MutableDomainModel
from app.core.models.candle import OHLCVCandle
from app.core.models.cross_feature_observation import CrossFeatureObservation
from app.core.models.data_quality import DataQuality
from app.core.models.decision import TradeDecision
from app.core.models.feature_status import FeatureStatus
from app.core.models.flow_feature_snapshot import FlowFeatureSnapshot
from app.core.models.funding import FundingRate
from app.core.models.funding_features import FundingFeatures, FundingWindowFeatures
from app.core.models.instrument import InstrumentMetadata
from app.core.models.judge import JudgeVerdict
from app.core.models.liquidation import LiquidationEvent
from app.core.models.liquidation_features import LiquidationWindowFeatures
from app.core.models.market_snapshot import MarketSnapshot
from app.core.models.money_management import MoneyManagementDecision
from app.core.models.open_interest import OpenInterest
from app.core.models.open_interest_features import OpenInterestFeatures, OpenInterestWindowFeatures
from app.core.models.order_book import OrderBookDeltaEvent, OrderBookLevel, OrderBookSnapshot
from app.core.models.order_book_features import DepthBand, DepthBandFeatures, OrderBookFeatures
from app.core.models.performance import PerformanceSnapshot
from app.core.models.position import PositionRecord
from app.core.models.price_context_features import PriceContextWindowFeatures
from app.core.models.quote import BidAskQuote, PriceQuote
from app.core.models.risk import RiskAssessment
from app.core.models.stream_health import StreamHealth
from app.core.models.taker_flow import TakerFlowSnapshot
from app.core.models.taker_flow_features import TakerFlowWindowFeatures
from app.core.models.technical import TechnicalSnapshot
from app.core.models.trade_event import TradeEvent
from app.core.models.trade_setup import EntryZone, TradeSetup

__all__ = [
    "AgentAssessment",
    "AnalyticsWindow",
    "BidAskQuote",
    "CrossFeatureObservation",
    "DataQuality",
    "DepthBand",
    "DepthBandFeatures",
    "DomainModel",
    "EntryZone",
    "FeatureStatus",
    "FlowFeatureSnapshot",
    "FundingFeatures",
    "FundingRate",
    "FundingWindowFeatures",
    "InstrumentMetadata",
    "JudgeVerdict",
    "LiquidationEvent",
    "LiquidationWindowFeatures",
    "MarketSnapshot",
    "MoneyManagementDecision",
    "MutableDomainModel",
    "OHLCVCandle",
    "OpenInterest",
    "OpenInterestFeatures",
    "OpenInterestWindowFeatures",
    "OrderBookDeltaEvent",
    "OrderBookFeatures",
    "OrderBookLevel",
    "OrderBookSnapshot",
    "PerformanceSnapshot",
    "PositionRecord",
    "PriceContextWindowFeatures",
    "PriceQuote",
    "RiskAssessment",
    "StreamHealth",
    "TakerFlowSnapshot",
    "TakerFlowWindowFeatures",
    "TechnicalSnapshot",
    "TradeDecision",
    "TradeEvent",
    "TradeSetup",
]
