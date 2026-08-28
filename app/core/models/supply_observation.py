"""Stage 4E provider-neutral asset-supply fact.

One provider-reported observation of one asset's supply on one network, at
one point/period. Facts only - ``circulating_supply`` is never claimed to be
cross-provider canonical: "circulating" embeds a provider's own methodology
for which coins count as locked/lost/circulating, exactly as
``app.core.models.economic_event`` never claims a canonical cross-provider
event id.

Both ``total_supply``/``circulating_supply`` are always in native-asset
units by definition of what "supply" means - no separate unit field exists
on this model (unlike ``app.core.models.network_activity_observation``,
where the same underlying quantity can genuinely vary in representation
across providers).

Identity across versions is ``(provider, provider_series_id, asset, network,
observation_time)`` - see ``app.onchain.history`` for version-preserving
handling. No ``revision_number`` - mirrors
``app.core.models.network_activity_observation``'s reasoning.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Self

from pydantic import Field, model_validator

from app.core.models.base import DomainModel, Timestamp
from app.core.models.instrument import Asset


class SupplyObservation(DomainModel):
    """One provider-reported supply observation, at one version."""

    provider: str = Field(min_length=1)
    provider_series_id: str = Field(min_length=1)
    asset: Asset
    network: str = Field(min_length=1)
    observation_time: Timestamp
    period_start: Timestamp | None = None
    period_end: Timestamp | None = None
    publication_time: Timestamp | None = None
    received_at: Timestamp
    total_supply: Annotated[Decimal, Field(ge=0)] | None = None
    circulating_supply: Annotated[Decimal, Field(ge=0)] | None = None

    @model_validator(mode="after")
    def _validate_period_window_pairing(self) -> Self:
        if (self.period_start is None) != (self.period_end is None):
            raise ValueError("period_start and period_end must both be set or both be unset")
        return self

    @model_validator(mode="after")
    def _validate_at_least_one_supply_value(self) -> Self:
        if self.total_supply is None and self.circulating_supply is None:
            raise ValueError("at least one of total_supply/circulating_supply must be set")
        return self


__all__ = ["SupplyObservation"]
