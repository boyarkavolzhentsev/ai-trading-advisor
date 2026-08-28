"""Stage 4F analyst contracts.

Four narrow, synchronous, ``runtime_checkable`` Protocols - one per analyst,
not one shared ``analyze(snapshot)`` Protocol - because the four analysts'
inputs are genuinely different shapes (event lists vs. rate/yield lists vs.
news+sentiment lists vs. four on-chain observation-list families). Flow's/
Technical's single-Protocol design is enabled by every analyst sharing one
input shape (one snapshot type); Stage 4F has no such shared shape to hang
one Protocol signature on, so forcing one generic ``analyze(*args)`` or a
dict-based input would defeat the whole point of a structural contract -
see the Stage 4F design report, "Package/file architecture".
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import ClassVar, Protocol, runtime_checkable

from app.core.enums.external_intelligence_analysis import ExternalIntelligenceAnalystType
from app.core.models.base import Symbol, Timestamp
from app.core.models.economic_event import CurrencyCode, EconomicEvent
from app.core.models.exchange_flow_observation import ExchangeFlowObservation
from app.core.models.external_intelligence_analysis_result import ExternalIntelligenceAnalysisResult
from app.core.models.government_yield_observation import GovernmentYieldObservation
from app.core.models.instrument import Asset
from app.core.models.network_activity_observation import NetworkActivityObservation
from app.core.models.news_item import NewsItem
from app.core.models.news_sentiment_observation import NewsSentimentObservation
from app.core.models.policy_rate_observation import PolicyRateObservation
from app.core.models.stablecoin_supply_observation import StablecoinSupplyObservation
from app.core.models.supply_observation import SupplyObservation
from app.external_intelligence_analysts.config import (
    MacroAnalystConfig,
    NewsSentimentAnalystConfig,
    OnChainAnalystConfig,
    RatesYieldAnalystConfig,
)


@runtime_checkable
class MacroEventAnalystProtocol(Protocol):
    """Stateless, synchronous, provider-agnostic macro-event specialist."""

    analyst_type: ClassVar[ExternalIntelligenceAnalystType]

    def analyze(
        self,
        events: Sequence[EconomicEvent],
        *,
        currency: CurrencyCode,
        analysis_time: Timestamp,
        config: MacroAnalystConfig,
    ) -> ExternalIntelligenceAnalysisResult: ...


@runtime_checkable
class RatesYieldAnalystProtocol(Protocol):
    """Stateless, synchronous, provider-agnostic rates/yield specialist."""

    analyst_type: ClassVar[ExternalIntelligenceAnalystType]

    def analyze(
        self,
        policy_rates: Sequence[PolicyRateObservation],
        yields: Sequence[GovernmentYieldObservation],
        *,
        currency: CurrencyCode,
        analysis_time: Timestamp,
        config: RatesYieldAnalystConfig,
    ) -> ExternalIntelligenceAnalysisResult: ...


@runtime_checkable
class NewsSentimentAnalystProtocol(Protocol):
    """Stateless, synchronous, provider-agnostic news/sentiment specialist."""

    analyst_type: ClassVar[ExternalIntelligenceAnalystType]

    def analyze(
        self,
        news_items: Sequence[NewsItem],
        sentiment_observations: Sequence[NewsSentimentObservation],
        *,
        symbol: Symbol,
        analysis_time: Timestamp,
        config: NewsSentimentAnalystConfig,
    ) -> ExternalIntelligenceAnalysisResult: ...


@runtime_checkable
class OnChainAnalystProtocol(Protocol):
    """Stateless, synchronous, provider-agnostic on-chain specialist."""

    analyst_type: ClassVar[ExternalIntelligenceAnalystType]

    def analyze(
        self,
        network_activity: Sequence[NetworkActivityObservation],
        supply: Sequence[SupplyObservation],
        exchange_flows: Sequence[ExchangeFlowObservation],
        stablecoin_supply: Sequence[StablecoinSupplyObservation],
        *,
        asset: Asset,
        network: str,
        analysis_time: Timestamp,
        config: OnChainAnalystConfig,
    ) -> ExternalIntelligenceAnalysisResult: ...


__all__ = [
    "MacroEventAnalystProtocol",
    "NewsSentimentAnalystProtocol",
    "OnChainAnalystProtocol",
    "RatesYieldAnalystProtocol",
]
