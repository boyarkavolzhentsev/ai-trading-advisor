"""Provider-agnostic economic-calendar contract (Stage 4A).

Mirrors ``app.market_data.protocols``'s style: a narrow, single-capability,
``runtime_checkable`` ``Protocol`` with a plain synchronous method returning
typed domain models, raising ``EconomicDataError`` subclasses on failure.
Economic-calendar releases are discrete, low-frequency, polled facts - there
is no continuous-stream requirement analogous to the Stage 1C real-time
layer, so this Protocol stays synchronous by design (see the Stage 4A design
report, "Async/sync architecture").

Sibling protocols for rates, news, sentiment and on-chain data belong to
their own later stages and are deliberately not stubbed here.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from app.core.enums.economic_calendar import EconomicCategory
from app.core.models.base import Timestamp
from app.core.models.economic_event import EconomicEvent

DEFAULT_EVENT_LIMIT = 100
"""Number of events requested when the caller does not specify a limit."""


@runtime_checkable
class EconomicCalendarProvider(Protocol):
    """Read-only source of economic-calendar events for one range of time."""

    def get_events(
        self,
        start: Timestamp,
        end: Timestamp,
        *,
        countries: Sequence[str] | None = None,
        categories: Sequence[EconomicCategory] | None = None,
        limit: int = DEFAULT_EVENT_LIMIT,
    ) -> list[EconomicEvent]:
        """Return up to ``limit`` events with ``event_time`` in ``[start, end]``."""
        ...


__all__ = ["DEFAULT_EVENT_LIMIT", "EconomicCalendarProvider"]
