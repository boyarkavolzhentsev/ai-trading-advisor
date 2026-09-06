"""Durable Final Recommendation provenance output contract (Final Runtime
Integration, Part E corrective design).

``FinalRecommendationProvenance`` is the sole durable carrier of the three
``FinalRecommendation`` facts that never survive into Stage 10E's own
persisted state - ``PositionRecord``/``MT5TrackedRecommendation`` carry
neither ``family``, ``approved_risk_amount``, nor ``account_currency`` (see
the approved Part E corrective design). Every other ``FinalRecommendation``
field already round-trips unchanged through the existing, unmodified
``MT5TrackedRecommendation``/``PositionRecord`` persisted state, so this
model deliberately never duplicates any of them.

Immutable: provenance is a point-in-time snapshot fact captured once, at
issuance, and never updated afterward - unlike ``MT5TrackedRecommendation``'s
own genuinely mutable lifecycle state. ``account_currency`` always
accompanies ``approved_risk_amount`` on the same record (the amount is
uninterpretable without its currency) - never persisted independently of it.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from pydantic import Field

from app.core.enums.strategy_router import StrategyFamily
from app.core.models.base import DomainModel


class FinalRecommendationProvenance(DomainModel):
    """One ``trade_id``'s durable recommendation-issuance provenance.

    Every field is an unchanged copy of the originating ``FinalRecommendation``
    - never rounded, converted, normalized, or hardcoded. No FX rate is ever
    fetched or computed to produce ``account_currency``: it is always the
    exact, unchanged, broker-reported ``MT5AccountFacts.currency`` value the
    originating ``FinalRecommendation`` itself already carried.
    """

    trade_id: Annotated[str, Field(min_length=1)]
    family: StrategyFamily
    approved_risk_amount: Annotated[Decimal, Field(gt=0)]
    account_currency: Annotated[str, Field(min_length=1)]


__all__ = ["FinalRecommendationProvenance"]
