"""Stage 4B: provider-agnostic rates/yields facts.

Normalized facts only - no interpretation, no analyst, no supervisor, no real
HTTP provider integration. Layering mirrors ``app.macro``:

1. two provider Protocols (``PolicyRateProvider``, ``GovernmentYieldProvider``)
   future concrete adapters satisfy;
2. domain contracts (``app.core.models.policy_rate_observation.PolicyRateObservation``,
   ``app.core.models.government_yield_observation.GovernmentYieldObservation``,
   ``app.core.models.tenor.Tenor``);
3. ``app.rates.history`` - two bounded, append-only, revision-preserving
   observation logs.

No lifecycle-inference helper exists here (unlike Stage 4A's
``app.macro.quality.infer_status``): a continuous rates/yields time series
has no scheduled/postponed/cancelled state machine to infer.

Independent from ``app.flow*`` and ``app.technical*`` - see
``tests/test_rates_no_flow_coupling.py`` and
``tests/test_rates_no_technical_coupling.py``. Also independent from
``app.macro``'s history/protocol/quality machinery: the two packages share
only genuinely generic Stage 4A vocabulary (``CentralBank``, ``CountryCode``,
``CurrencyCode``), never behavior.
"""

from __future__ import annotations

from app.rates.exceptions import (
    DuplicateObservationError,
    InvalidProviderResponseError,
    ProviderUnavailableError,
    RatesDataError,
    RevisionConflictError,
    UnknownSeriesError,
)
from app.rates.history import (
    DEFAULT_CAPACITY,
    GovernmentYieldObservationHistory,
    PolicyRateObservationHistory,
)
from app.rates.protocols import DEFAULT_OBSERVATION_LIMIT, GovernmentYieldProvider, PolicyRateProvider
from app.rates.provenance import RatesDataSource, RatesProvenance

__all__ = [
    "DEFAULT_CAPACITY",
    "DEFAULT_OBSERVATION_LIMIT",
    "DuplicateObservationError",
    "GovernmentYieldObservationHistory",
    "GovernmentYieldProvider",
    "InvalidProviderResponseError",
    "PolicyRateObservationHistory",
    "PolicyRateProvider",
    "ProviderUnavailableError",
    "RatesDataError",
    "RatesDataSource",
    "RatesProvenance",
    "RevisionConflictError",
    "UnknownSeriesError",
]
