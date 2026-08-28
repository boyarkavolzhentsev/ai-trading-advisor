"""Origin record of one on-chain fetch (Stage 4E).

Parallel to ``app.news.provenance.NewsProvenance`` but scoped to Stage 4E
on-chain facts - not reused directly because ``NewsDataSource`` is a closed
vocabulary of news-feed endpoint kinds that should not grow on-chain members
onto it. A standalone, per-fetch audit record - not embedded inside any of
the four observation models, mirroring how no sibling provenance model is
embedded inside its fact model.

Answers who supplied a fetch, which endpoint kind, and when - not what
asset/network/exchange it refers to, which already lives on the fact model
itself (mirrors ``MacroProvenance`` not duplicating ``country``/``currency``).

No confidence/reliability/credibility/probability/importance/impact
classification lives here, and no ``origin`` field: every Stage 4E
observation is externally supplied/provider-native by definition, so a
field that would read the same value on every record adds nothing (mirrors
the Stage 4D review's rejection of ``SentimentOrigin``).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from app.core.models.base import DomainModel, Timestamp


class OnChainDataSource(StrEnum):
    """Kind of endpoint one on-chain record was fetched from."""

    NETWORK_ACTIVITY = "NETWORK_ACTIVITY"
    SUPPLY = "SUPPLY"
    EXCHANGE_FLOW = "EXCHANGE_FLOW"
    STABLECOIN_SUPPLY = "STABLECOIN_SUPPLY"


class OnChainProvenance(DomainModel):
    """Where one on-chain fetch came from, and when."""

    provider: str = Field(min_length=1)
    source: OnChainDataSource
    fetched_at: Timestamp
    provider_timestamp: Timestamp | None = None
    source_url: str | None = Field(default=None, min_length=1)

    @property
    def label(self) -> str:
        """Compact ``provider:source`` label, mirroring ``NewsProvenance.label``."""
        return f"{self.provider}:{self.source.value}"


__all__ = ["OnChainDataSource", "OnChainProvenance"]
