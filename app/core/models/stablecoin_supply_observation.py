"""Stage 4E provider-neutral stablecoin-supply fact.

One provider-reported observation of one stablecoin's supply and/or
mint/burn activity on one network, at one point/period. Facts only - no
liquidity-conditions or risk-on/risk-off interpretation of any kind.

Reuses ``app.core.models.instrument.Asset`` for the stablecoin's own ticker
(e.g. ``USDT``) and a free-form ``network`` for its host chain - the same
stablecoin asset legitimately has independent supply pools on multiple
networks (``USDT`` on ``ethereum`` vs. ``tron``), so no dedicated
"stablecoin identity" type is introduced; a stablecoin's exchange flows
reuse ``app.core.models.exchange_flow_observation.ExchangeFlowObservation``
directly (it is already asset-agnostic) rather than a second model.

``total_supply``/``circulating_supply``/``mint_amount``/``burn_amount`` are
always in native-asset (token) units by definition - no unit field exists
on this model, mirroring
``app.core.models.supply_observation.SupplyObservation``.

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


class StablecoinSupplyObservation(DomainModel):
    """One provider-reported stablecoin-supply observation, at one version."""

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
    mint_amount: Annotated[Decimal, Field(ge=0)] | None = None
    burn_amount: Annotated[Decimal, Field(ge=0)] | None = None

    @model_validator(mode="after")
    def _validate_period_window_pairing(self) -> Self:
        if (self.period_start is None) != (self.period_end is None):
            raise ValueError("period_start and period_end must both be set or both be unset")
        return self

    @model_validator(mode="after")
    def _validate_at_least_one_value(self) -> Self:
        if (
            self.total_supply is None
            and self.circulating_supply is None
            and self.mint_amount is None
            and self.burn_amount is None
        ):
            raise ValueError(
                "at least one of total_supply/circulating_supply/mint_amount/burn_amount must be set"
            )
        return self


__all__ = ["StablecoinSupplyObservation"]
