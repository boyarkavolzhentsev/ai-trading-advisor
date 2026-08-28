"""Stage 4E provider-classified exchange-flow fact.

One provider-reported observation of exchange-classified inflow, outflow,
and/or balance/reserve for one ``(asset, network)``, at one point/period.

These are PROVIDER-CLASSIFIED facts, not independently verified ground
truth: deciding which on-chain addresses belong to an exchange is the
reporting provider's own knowledge/methodology, exactly as
``app.core.models.economic_event``'s facts are the provider's own reported
values, never re-derived or verified by this model. Accordingly this model
carries no ``verified``, ``ground_truth``, ``confidence``, ``reliability``,
or ``classification_quality`` field of any kind - there is nothing here
claiming an independent verification this package cannot actually perform.

``exchange=None`` means the provider reported this series as an aggregate
across all exchanges it tracks (no single-exchange dimension) - it is not
further interpreted as "no exchange activity" or any other conclusion.

Identity across versions is ``(provider, provider_series_id, asset, network,
exchange, observation_time)`` - ``exchange`` participates in identity
(including when ``None``) because a per-exchange series and the provider's
all-exchange aggregate are genuinely different, independently retained
facts, not versions of one another. No ``revision_number`` - mirrors
``app.core.models.network_activity_observation``'s reasoning.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Self

from pydantic import Field, model_validator

from app.core.enums.onchain import OnChainUnit
from app.core.models.base import DomainModel, Timestamp
from app.core.models.instrument import Asset


class ExchangeFlowObservation(DomainModel):
    """One provider-classified exchange-flow observation, at one version."""

    provider: str = Field(min_length=1)
    provider_series_id: str = Field(min_length=1)
    asset: Asset
    network: str = Field(min_length=1)
    exchange: str | None = Field(default=None, min_length=1)
    observation_time: Timestamp
    period_start: Timestamp | None = None
    period_end: Timestamp | None = None
    publication_time: Timestamp | None = None
    received_at: Timestamp
    inflow: Annotated[Decimal, Field(ge=0)] | None = None
    outflow: Annotated[Decimal, Field(ge=0)] | None = None
    balance: Annotated[Decimal, Field(ge=0)] | None = None
    unit: OnChainUnit | None = None

    @model_validator(mode="after")
    def _validate_period_window_pairing(self) -> Self:
        if (self.period_start is None) != (self.period_end is None):
            raise ValueError("period_start and period_end must both be set or both be unset")
        return self

    @model_validator(mode="after")
    def _validate_at_least_one_flow_value(self) -> Self:
        if self.inflow is None and self.outflow is None and self.balance is None:
            raise ValueError("at least one of inflow/outflow/balance must be set")
        return self

    @model_validator(mode="after")
    def _validate_unit_pairing(self) -> Self:
        any_value_present = self.inflow is not None or self.outflow is not None or self.balance is not None
        if any_value_present != (self.unit is not None):
            raise ValueError("unit must be set exactly when inflow/outflow/balance is set")
        return self


__all__ = ["ExchangeFlowObservation"]
