"""Stage 4E provider-neutral network-activity fact.

One provider-reported observation of network-level activity for one
``(asset, network)`` at one point/period. Facts only - no interpretation of
what a rise or fall in activity means.

``asset``/``network`` are independent, orthogonal dimensions - see the
Stage 4E design report, "Asset/network/entity identity design": the same
``asset`` (e.g. ``USDT``) can legitimately appear on multiple ``network``
values, and the same ``network`` is never assumed to imply one specific
``asset``.

``active_addresses``/``transaction_count`` are unconstrained-unit counts
(``int``) - a count has no ambiguous representation, so no separate unit
field exists for either. ``transaction_volume``/``fees_total`` can
legitimately be reported by different providers in native-asset units or in
USD, so each carries its own paired ``*_unit`` field - present together,
absent together, never rescaled or converted between units by this model.

Identity across versions is ``(provider, provider_series_id, asset, network,
observation_time)`` - see ``app.onchain.history`` for version-preserving
handling. There is no ``revision_number``: on-chain indexers commonly revise
historical counts as reorgs resolve and confirmations accrue, but expose no
provider-native revision counter and no "settled" state analogous to an
economic release - mirrors ``app.news.history``'s reasoning, not
``app.macro.history``'s.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Self

from pydantic import Field, model_validator

from app.core.enums.onchain import OnChainUnit
from app.core.models.base import DomainModel, Timestamp
from app.core.models.instrument import Asset


class NetworkActivityObservation(DomainModel):
    """One provider-reported network-activity observation, at one version."""

    provider: str = Field(min_length=1)
    provider_series_id: str = Field(min_length=1)
    asset: Asset
    network: str = Field(min_length=1)
    observation_time: Timestamp
    period_start: Timestamp | None = None
    period_end: Timestamp | None = None
    publication_time: Timestamp | None = None
    received_at: Timestamp
    active_addresses: Annotated[int, Field(ge=0)] | None = None
    transaction_count: Annotated[int, Field(ge=0)] | None = None
    transaction_volume: Annotated[Decimal, Field(ge=0)] | None = None
    transaction_volume_unit: OnChainUnit | None = None
    fees_total: Annotated[Decimal, Field(ge=0)] | None = None
    fees_unit: OnChainUnit | None = None

    @model_validator(mode="after")
    def _validate_period_window_pairing(self) -> Self:
        if (self.period_start is None) != (self.period_end is None):
            raise ValueError("period_start and period_end must both be set or both be unset")
        return self

    @model_validator(mode="after")
    def _validate_transaction_volume_unit_pairing(self) -> Self:
        if (self.transaction_volume is None) != (self.transaction_volume_unit is None):
            raise ValueError("transaction_volume and transaction_volume_unit must both be set or both be unset")
        return self

    @model_validator(mode="after")
    def _validate_fees_unit_pairing(self) -> Self:
        if (self.fees_total is None) != (self.fees_unit is None):
            raise ValueError("fees_total and fees_unit must both be set or both be unset")
        return self

    @model_validator(mode="after")
    def _validate_at_least_one_activity_metric(self) -> Self:
        if (
            self.active_addresses is None
            and self.transaction_count is None
            and self.transaction_volume is None
            and self.fees_total is None
        ):
            raise ValueError(
                "at least one of active_addresses/transaction_count/transaction_volume/fees_total must be set"
            )
        return self


__all__ = ["NetworkActivityObservation"]
