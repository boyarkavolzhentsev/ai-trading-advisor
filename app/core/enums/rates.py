"""Stage 4B rates/yields enums - normalized facts only, no interpretation.

No member here encodes a trend, rising/falling classification, or
qualitative policy-stance judgment - see
``app.core.models.policy_rate_observation`` and
``app.core.models.government_yield_observation`` for the facts-only
contracts this vocabulary backs.
"""

from __future__ import annotations

from enum import StrEnum


class TenorUnit(StrEnum):
    """Unit a ``Tenor`` was expressed in by its constructor.

    Distinct from ``Tenor``'s canonical total-months identity: two tenors
    expressed under different units may be economically identical
    (``Tenor.of_months(24) == Tenor.of_years(2)``) while carrying different
    ``unit`` values - ``unit`` records how the tenor was constructed, not
    part of its equality/hash identity.
    """

    MONTHS = "MONTHS"
    YEARS = "YEARS"


class PolicyRateKind(StrEnum):
    """Which specific policy-rate quantity one observation reports.

    A central bank publishing a target *range* (e.g. the Fed) is represented
    as two separate observations - ``TARGET_LOWER`` and ``TARGET_UPPER`` -
    never averaged into one ambiguous number. A central bank publishing one
    point target (e.g. the ECB deposit facility rate) uses ``TARGET``.
    ``EFFECTIVE`` is the realized market rate (e.g. EFFR), distinct from any
    target.
    """

    TARGET = "TARGET"
    TARGET_LOWER = "TARGET_LOWER"
    TARGET_UPPER = "TARGET_UPPER"
    EFFECTIVE = "EFFECTIVE"


class GovernmentYieldType(StrEnum):
    """Whether one yield observation is nominal or inflation-adjusted (real)."""

    NOMINAL = "NOMINAL"
    REAL = "REAL"


class SeriesUnit(StrEnum):
    """Unit a rates/yields observation's ``value`` is expressed in.

    Deliberately closed to only what Stage 4B needs: no index-points member
    exists here because currency-index facts (e.g. DXY) are out of scope for
    this stage.
    """

    PERCENT = "PERCENT"
    BASIS_POINTS = "BASIS_POINTS"


__all__ = ["GovernmentYieldType", "PolicyRateKind", "SeriesUnit", "TenorUnit"]
