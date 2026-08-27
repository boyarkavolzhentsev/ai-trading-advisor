"""Typed domain contracts exchanged between components."""

from __future__ import annotations

from app.core.models.analytics_window import AnalyticsWindow
from app.core.models.assessment import AgentAssessment
from app.core.models.base import DomainModel, MutableDomainModel
from app.core.models.candle import OHLCVCandle
from app.core.models.candle_structure_features import CandleStructureFeatures
from app.core.models.cross_feature_observation import CrossFeatureObservation
from app.core.models.data_quality import DataQuality
from app.core.models.decision import TradeDecision
from app.core.models.economic_event import EconomicEvent, RateDecisionDetail
from app.core.models.feature_status import FeatureStatus
from app.core.models.flow_analysis_result import FlowAnalysisObservation, FlowAnalysisResult
from app.core.models.flow_evidence import FlowEvidence
from app.core.models.flow_feature_snapshot import FlowFeatureSnapshot
from app.core.models.funding import FundingRate
from app.core.models.funding_features import FundingFeatures, FundingWindowFeatures
from app.core.models.instrument import InstrumentMetadata
from app.core.models.judge import JudgeVerdict
from app.core.models.liquidation import LiquidationEvent
from app.core.models.liquidation_features import LiquidationWindowFeatures
from app.core.models.market_snapshot import MarketSnapshot
from app.core.models.market_structure_features import MarketStructureFeatures, StructuralBreak, SwingPoint
from app.core.models.momentum_features import MomentumFeatures
from app.core.models.money_management import MoneyManagementDecision
from app.core.models.moving_average_features import MovingAverageFeatures
from app.core.models.open_interest import OpenInterest
from app.core.models.open_interest_features import OpenInterestFeatures, OpenInterestWindowFeatures
from app.core.models.order_book import OrderBookDeltaEvent, OrderBookLevel, OrderBookSnapshot
from app.core.models.order_book_features import DepthBand, DepthBandFeatures, OrderBookFeatures
from app.core.models.performance import PerformanceSnapshot
from app.core.models.position import PositionRecord
from app.core.models.price_context_features import PriceContextWindowFeatures
from app.core.models.quote import BidAskQuote, PriceQuote
from app.core.models.range_state_features import RangeStateFeatures
from app.core.models.risk import RiskAssessment
from app.core.models.stream_health import StreamHealth
from app.core.models.taker_flow import TakerFlowSnapshot
from app.core.models.taker_flow_features import TakerFlowWindowFeatures
from app.core.models.technical import TechnicalSnapshot
from app.core.models.technical_feature_snapshot import TechnicalFeatureSnapshot
from app.core.models.trade_event import TradeEvent
from app.core.models.trade_setup import EntryZone, TradeSetup
from app.core.models.trend_features import TrendFeatures
from app.core.models.volatility_features import VolatilityFeatures

__all__ = [
    "AgentAssessment",
    "AnalyticsWindow",
    "BidAskQuote",
    "CandleStructureFeatures",
    "CrossFeatureObservation",
    "DataQuality",
    "DepthBand",
    "DepthBandFeatures",
    "DomainModel",
    "EconomicEvent",
    "EntryZone",
    "FeatureStatus",
    "FlowAnalysisObservation",
    "FlowAnalysisResult",
    "FlowEvidence",
    "FlowFeatureSnapshot",
    "FundingFeatures",
    "FundingRate",
    "FundingWindowFeatures",
    "InstrumentMetadata",
    "JudgeVerdict",
    "LiquidationEvent",
    "LiquidationWindowFeatures",
    "MarketSnapshot",
    "MarketStructureFeatures",
    "MomentumFeatures",
    "MoneyManagementDecision",
    "MovingAverageFeatures",
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
    "RangeStateFeatures",
    "RateDecisionDetail",
    "RiskAssessment",
    "StreamHealth",
    "StructuralBreak",
    "SwingPoint",
    "TakerFlowSnapshot",
    "TakerFlowWindowFeatures",
    "TechnicalFeatureSnapshot",
    "TechnicalSnapshot",
    "TradeDecision",
    "TradeEvent",
    "TradeSetup",
    "TrendFeatures",
    "VolatilityFeatures",
]
