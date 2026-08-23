"""Deterministic order-book / microstructure feature contract.

``DepthBand`` names either a fixed level count (``top_n``) or a max distance
from mid in basis points (``max_distance_bps``) - never both, so a
``DepthBandFeatures`` entry is unambiguous about what it measured. Weighted
(distance-discounted) imbalance is explicitly deferred; only the unweighted
``depth_imbalance`` is computed in Stage 2A.

Fake-precision guard: if the available order book does not reach a
requested ``max_distance_bps`` boundary (or does not have ``top_n`` levels
on a side), that band's ``status.quality`` is ``PARTIAL`` - the figure is
never reported as if it represented the full requested band.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Self

from pydantic import Field, model_validator

from app.core.enums.instrument import ContractType
from app.core.models.base import DomainModel, Price, Symbol, Timestamp
from app.core.models.feature_status import FeatureStatus


class DepthBand(DomainModel):
    """One depth-band spec: exactly one of ``top_n`` or ``max_distance_bps``."""

    label: str = Field(min_length=1)
    top_n: int | None = None
    max_distance_bps: Decimal | None = None

    @model_validator(mode="after")
    def _validate_exactly_one(self) -> Self:
        if (self.top_n is None) == (self.max_distance_bps is None):
            raise ValueError("exactly one of top_n or max_distance_bps must be set")
        if self.top_n is not None and self.top_n <= 0:
            raise ValueError("top_n must be positive")
        if self.max_distance_bps is not None and self.max_distance_bps <= 0:
            raise ValueError("max_distance_bps must be positive")
        return self


class DepthBandFeatures(DomainModel):
    """Depth/imbalance features of one book side pair within one ``DepthBand``."""

    band: DepthBand
    bid_depth: Decimal | None = None
    ask_depth: Decimal | None = None
    depth_imbalance: float | None = None
    bid_depth_change: dict[str, Decimal] = Field(default_factory=dict)
    ask_depth_change: dict[str, Decimal] = Field(default_factory=dict)
    status: FeatureStatus


class OrderBookFeatures(DomainModel):
    """Point-in-time order-book microstructure features of one symbol."""

    symbol: Symbol
    contract_type: ContractType
    as_of: Timestamp
    best_bid: Price | None = None
    best_ask: Price | None = None
    spread: Decimal | None = None
    spread_bps: Decimal | None = None
    mid_price: Price | None = None
    bands: dict[str, DepthBandFeatures] = Field(default_factory=dict)
    status: FeatureStatus
    source: str = Field(min_length=1)
