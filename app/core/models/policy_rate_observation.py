"""Stage 4B policy-rate time-series fact.

One provider-reported observation of a central bank's policy-rate quantity
at one point in time. Facts only - no qualitative policy-stance
interpretation of any kind, and no rate-change magnitude.

Deliberately independent from ``app.core.models.economic_event.RateDecisionDetail``:
that model is a point-in-time snapshot attached to one scheduled
``RATE_DECISION`` calendar event (previous/expected/actual around one
meeting); ``PolicyRateObservation`` is the standalone, continuously
queryable rate time series, independently sourced and not required to be
1:1 with any calendar event. Neither model references the other.

``value`` is unconstrained ``Decimal | None`` - unlike ``Price``/``Money``,
a policy rate may legitimately be negative (ECB/BOJ negative-rate policy).
``None`` means the provider did not supply a value for this observation;
``Decimal("0")`` is always a real, valid rate (zero-bound policy).

Identity is ``(provider, provider_series_id, observation_time,
revision_number)`` - see ``app.rates.history`` for append-only revision
handling.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from pydantic import Field

from app.core.enums.economic_calendar import CentralBank
from app.core.enums.rates import PolicyRateKind, SeriesUnit
from app.core.models.base import DomainModel, Timestamp
from app.core.models.economic_event import CurrencyCode


class PolicyRateObservation(DomainModel):
    """One provider-reported policy-rate observation, at one revision."""

    provider: str = Field(min_length=1)
    provider_series_id: str = Field(min_length=1)
    central_bank: CentralBank
    currency: CurrencyCode
    rate_kind: PolicyRateKind
    value: Decimal | None = None
    unit: SeriesUnit
    observation_time: Timestamp
    publication_time: Timestamp | None = None
    received_at: Timestamp
    revision_number: Annotated[int, Field(ge=0)] = 0
    source_url: str | None = Field(default=None, min_length=1)


__all__ = ["PolicyRateObservation"]
