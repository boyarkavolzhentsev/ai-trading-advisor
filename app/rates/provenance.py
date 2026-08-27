"""Origin record of one rates/yields fetch (Stage 4B).

Parallel to ``app.macro.provenance.MacroProvenance`` but scoped to Stage 4B
rates/yields facts - not reused directly because ``EconomicDataSource`` is a
closed vocabulary of economic-calendar endpoint kinds that should not grow
rates/yields members onto it. A standalone, per-fetch audit record - not
embedded inside ``PolicyRateObservation``/``GovernmentYieldObservation``,
mirroring how ``MacroProvenance`` is not embedded inside ``EconomicEvent``.

No reliability/quality classification lives here, mirroring Stage 4A.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from app.core.models.base import DomainModel, Timestamp


class RatesDataSource(StrEnum):
    """Kind of endpoint one rates/yields record was fetched from."""

    POLICY_RATE = "POLICY_RATE"
    GOVERNMENT_YIELD = "GOVERNMENT_YIELD"


class RatesProvenance(DomainModel):
    """Where one rates/yields fetch came from, and when."""

    provider: str = Field(min_length=1)
    source: RatesDataSource
    fetched_at: Timestamp
    provider_timestamp: Timestamp | None = None
    source_url: str | None = Field(default=None, min_length=1)

    @property
    def label(self) -> str:
        """Compact ``provider:source`` label, mirroring ``MacroProvenance.label``."""
        return f"{self.provider}:{self.source.value}"


__all__ = ["RatesDataSource", "RatesProvenance"]
