"""Stage 4B government-yield time-series fact.

One provider-reported observation of one government yield - nominal or
real - at one tenor, at one point in time. Facts only - no curve
interpretation and no directional classification of any kind.

Nominal and real yields share this one model, distinguished by
``yield_type``: they have identical shape (country, currency, tenor, value,
unit) and differ only in which underlying instrument class the value comes
from (a nominal government bond vs. an inflation-protected security), never
in structure.

``value`` is unconstrained ``Decimal | None`` - a real yield may legitimately
be negative. ``None`` means the provider did not supply a value; a genuine
``Decimal("0")`` is always a real, valid observation.

Identity is ``(provider, provider_series_id, observation_time,
revision_number)`` - see ``app.rates.history`` for append-only revision
handling. No US-only assumption: ``country``/``currency`` are provider-
reported, not hardcoded or defaulted.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from pydantic import Field

from app.core.enums.rates import GovernmentYieldType, SeriesUnit
from app.core.models.base import DomainModel, Timestamp
from app.core.models.economic_event import CountryCode, CurrencyCode
from app.core.models.tenor import Tenor


class GovernmentYieldObservation(DomainModel):
    """One provider-reported government-yield observation, at one revision."""

    provider: str = Field(min_length=1)
    provider_series_id: str = Field(min_length=1)
    country: CountryCode
    currency: CurrencyCode
    yield_type: GovernmentYieldType
    tenor: Tenor
    value: Decimal | None = None
    unit: SeriesUnit
    observation_time: Timestamp
    publication_time: Timestamp | None = None
    received_at: Timestamp
    revision_number: Annotated[int, Field(ge=0)] = 0
    source_url: str | None = Field(default=None, min_length=1)


__all__ = ["GovernmentYieldObservation"]
