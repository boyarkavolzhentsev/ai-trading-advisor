"""Stage 4A: provider-agnostic economic-calendar facts.

Normalized facts only - no interpretation, no analyst, no supervisor, no real
HTTP provider integration. Layering mirrors ``app.market_data``:

1. a provider Protocol (``EconomicCalendarProvider``) future concrete
   adapters satisfy;
2. domain contracts (``app.core.models.economic_event.EconomicEvent``,
   ``RateDecisionDetail``);
3. ``app.macro.quality`` - a pure lifecycle-inference helper;
4. ``app.macro.history`` - a bounded, append-only, revision-preserving event
   log.

Independent from ``app.flow*`` and ``app.technical*`` - see
``tests/test_macro_no_flow_coupling.py`` and
``tests/test_macro_no_technical_coupling.py``.
"""

from __future__ import annotations

from app.macro.exceptions import (
    DuplicateEventError,
    EconomicDataError,
    InvalidProviderResponseError,
    ProviderUnavailableError,
    RevisionConflictError,
    UnknownEventError,
)
from app.macro.history import DEFAULT_CAPACITY, EconomicEventHistory
from app.macro.protocols import DEFAULT_EVENT_LIMIT, EconomicCalendarProvider
from app.macro.provenance import EconomicDataSource, MacroProvenance
from app.macro.quality import infer_status

__all__ = [
    "DEFAULT_CAPACITY",
    "DEFAULT_EVENT_LIMIT",
    "DuplicateEventError",
    "EconomicCalendarProvider",
    "EconomicDataError",
    "EconomicDataSource",
    "EconomicEventHistory",
    "InvalidProviderResponseError",
    "MacroProvenance",
    "ProviderUnavailableError",
    "RevisionConflictError",
    "UnknownEventError",
    "infer_status",
]
