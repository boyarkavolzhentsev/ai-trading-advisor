"""Deterministic crypto flow analytics composition root.

One ``FlowFeatureSnapshot`` per ``(symbol, contract_type)`` observation:
every nested block shares the same ``observation_time`` and the same
configured ``windows``, so a consumer never has to wonder whether two
numbers from different domains are comparable. Carries only already-computed
facts - no LONG/SHORT signal, no BUY/SELL recommendation, no interpretation.

``provenance`` maps a domain name (``"taker_flow"``, ``"liquidation"``,
``"order_book"``, ``"open_interest"``, ``"funding"``, ``"price_context"``) to
the ``source`` label its calculator was given, so a snapshot's origin stays
auditable even though its domains may come from different underlying
streams/polls.
"""

from __future__ import annotations

from pydantic import Field

from app.core.enums.instrument import ContractType
from app.core.models.analytics_window import AnalyticsWindow
from app.core.models.base import DomainModel, Symbol, Timestamp
from app.core.models.cross_feature_observation import CrossFeatureObservation
from app.core.models.funding_features import FundingFeatures
from app.core.models.liquidation_features import LiquidationWindowFeatures
from app.core.models.open_interest_features import OpenInterestFeatures
from app.core.models.order_book_features import OrderBookFeatures
from app.core.models.price_context_features import PriceContextWindowFeatures
from app.core.models.taker_flow_features import TakerFlowWindowFeatures


class FlowFeatureSnapshot(DomainModel):
    """Synchronized, multi-window deterministic flow analytics snapshot."""

    symbol: Symbol
    contract_type: ContractType
    observation_time: Timestamp
    windows: tuple[AnalyticsWindow, ...]
    taker_flow: dict[str, TakerFlowWindowFeatures] = Field(default_factory=dict)
    liquidation: dict[str, LiquidationWindowFeatures] = Field(default_factory=dict)
    order_book: OrderBookFeatures | None = None
    open_interest: OpenInterestFeatures | None = None
    funding: FundingFeatures | None = None
    price_context: dict[str, PriceContextWindowFeatures] = Field(default_factory=dict)
    cross_features: dict[str, CrossFeatureObservation] = Field(default_factory=dict)
    provenance: dict[str, str] = Field(default_factory=dict)
