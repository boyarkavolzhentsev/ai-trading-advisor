"""Origin record of one news fetch (Stage 4C).

Parallel to ``app.macro.provenance.MacroProvenance``/
``app.rates.provenance.RatesProvenance`` but scoped to Stage 4C news facts -
not reused directly because ``EconomicDataSource``/``RatesDataSource`` are
closed vocabularies of their own endpoint kinds that should not grow news
members onto them. A standalone, per-fetch audit record - not embedded
inside ``NewsItem``, mirroring how neither sibling provenance model is
embedded inside its fact model.

No reliability/confidence classification lives here, mirroring both
siblings: no reliability policy exists yet, and inventing one now would be
an unreviewed numeric/categorical judgment.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from app.core.models.base import DomainModel, Timestamp


class NewsDataSource(StrEnum):
    """Kind of endpoint one news record was fetched from.

    Deliberately a single member for now: no concrete provider integration
    exists yet to justify distinguishing e.g. ``PRESS_RELEASE``/
    ``WIRE_SERVICE`` members - add them later, deliberately, once real
    provider evidence exists (mirrors both siblings' stance on scope
    growth).
    """

    NEWS_FEED = "NEWS_FEED"


class NewsProvenance(DomainModel):
    """Where one news fetch came from, and when."""

    provider: str = Field(min_length=1)
    source: NewsDataSource
    fetched_at: Timestamp
    provider_timestamp: Timestamp | None = None
    source_url: str | None = Field(default=None, min_length=1)

    @property
    def label(self) -> str:
        """Compact ``provider:source`` label, mirroring ``MacroProvenance.label``."""
        return f"{self.provider}:{self.source.value}"


__all__ = ["NewsDataSource", "NewsProvenance"]
