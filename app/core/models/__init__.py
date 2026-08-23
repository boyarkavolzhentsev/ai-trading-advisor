"""Typed domain contracts exchanged between components."""

from __future__ import annotations

from app.core.models.assessment import AgentAssessment
from app.core.models.base import DomainModel, MutableDomainModel
from app.core.models.candle import OHLCVCandle
from app.core.models.data_quality import DataQuality
from app.core.models.decision import TradeDecision
from app.core.models.funding import FundingRate
from app.core.models.instrument import InstrumentMetadata
from app.core.models.judge import JudgeVerdict
from app.core.models.liquidation import LiquidationEvent
from app.core.models.market_snapshot import MarketSnapshot
from app.core.models.money_management import MoneyManagementDecision
from app.core.models.open_interest import OpenInterest
from app.core.models.order_book import OrderBookLevel, OrderBookSnapshot
from app.core.models.performance import PerformanceSnapshot
from app.core.models.position import PositionRecord
from app.core.models.quote import BidAskQuote, PriceQuote
from app.core.models.risk import RiskAssessment
from app.core.models.taker_flow import TakerFlowSnapshot
from app.core.models.technical import TechnicalSnapshot
from app.core.models.trade_setup import EntryZone, TradeSetup

__all__ = [
    "AgentAssessment",
    "BidAskQuote",
    "DataQuality",
    "DomainModel",
    "EntryZone",
    "FundingRate",
    "InstrumentMetadata",
    "JudgeVerdict",
    "LiquidationEvent",
    "MarketSnapshot",
    "MoneyManagementDecision",
    "MutableDomainModel",
    "OHLCVCandle",
    "OpenInterest",
    "OrderBookLevel",
    "OrderBookSnapshot",
    "PerformanceSnapshot",
    "PositionRecord",
    "PriceQuote",
    "RiskAssessment",
    "TakerFlowSnapshot",
    "TechnicalSnapshot",
    "TradeDecision",
    "TradeSetup",
]
