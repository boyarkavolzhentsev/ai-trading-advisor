"""Provider-agnostic rates/yields contracts (Stage 4B).

Mirrors ``app.macro.protocols``'s style: narrow, single-capability,
``runtime_checkable`` ``Protocol``s with a plain synchronous method
returning typed domain models, raising ``RatesDataError`` subclasses on
failure. Policy rates and government yields are discrete, low-frequency
(daily-to-intraday at most) polled facts - there is no continuous-stream
requirement analogous to the Stage 1C real-time layer, so both Protocols
stay synchronous by design.

Split into two narrow Protocols, not one combined provider - a policy-rate
source and a government-yield source are different capabilities, mirroring
how ``app.market_data.protocols`` splits by capability family rather than
exposing one god-interface.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.core.enums.economic_calendar import CentralBank
from app.core.enums.rates import GovernmentYieldType
from app.core.models.base import Timestamp
from app.core.models.economic_event import CountryCode
from app.core.models.government_yield_observation import GovernmentYieldObservation
from app.core.models.policy_rate_observation import PolicyRateObservation
from app.core.models.tenor import Tenor

DEFAULT_OBSERVATION_LIMIT = 100
"""Number of observations requested when the caller does not specify a limit."""


@runtime_checkable
class PolicyRateProvider(Protocol):
    """Read-only source of one central bank's policy-rate observations."""

    def get_policy_rate(
        self,
        central_bank: CentralBank,
        start: Timestamp,
        end: Timestamp,
        *,
        limit: int = DEFAULT_OBSERVATION_LIMIT,
    ) -> list[PolicyRateObservation]:
        """Return up to ``limit`` observations with ``observation_time`` in ``[start, end]``."""
        ...


@runtime_checkable
class GovernmentYieldProvider(Protocol):
    """Read-only source of one country's government-yield observations."""

    def get_government_yields(
        self,
        country: CountryCode,
        tenor: Tenor,
        start: Timestamp,
        end: Timestamp,
        *,
        yield_type: GovernmentYieldType = GovernmentYieldType.NOMINAL,
        limit: int = DEFAULT_OBSERVATION_LIMIT,
    ) -> list[GovernmentYieldObservation]:
        """Return up to ``limit`` observations with ``observation_time`` in ``[start, end]``."""
        ...


__all__ = ["DEFAULT_OBSERVATION_LIMIT", "GovernmentYieldProvider", "PolicyRateProvider"]
