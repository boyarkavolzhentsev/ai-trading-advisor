"""Origin record of one economic-calendar fetch.

Parallel to ``app.market_data.provenance.MarketDataProvenance`` but scoped to
Stage 4A macro facts - not reused directly because ``MarketDataSource`` is a
closed vocabulary of market-data endpoint kinds that should not grow
economic-calendar members onto it.

No reliability/quality classification lives here: no reliability policy
exists yet, and inventing one now would be an unreviewed numeric/categorical
judgment. Add it later, deliberately, if a defined policy is approved.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from app.core.models.base import DomainModel, Timestamp


class EconomicDataSource(StrEnum):
    """Kind of endpoint an economic-calendar record was fetched from."""

    ECONOMIC_CALENDAR = "ECONOMIC_CALENDAR"
    RATE_DECISION = "RATE_DECISION"


class MacroProvenance(DomainModel):
    """Where one economic-calendar fetch came from, and when."""

    provider: str = Field(min_length=1)
    source: EconomicDataSource
    fetched_at: Timestamp
    provider_timestamp: Timestamp | None = None
    source_url: str | None = Field(default=None, min_length=1)

    @property
    def label(self) -> str:
        """Compact ``provider:source`` label, mirroring ``MarketDataProvenance.label``."""
        return f"{self.provider}:{self.source.value}"


__all__ = ["EconomicDataSource", "MacroProvenance"]
