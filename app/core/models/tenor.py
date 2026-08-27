"""Validated tenor value object for Stage 4B rates/yields facts.

Canonicalized to total months so that economically-identical tenors
reported under different units by different providers compare equal
(``Tenor.of_months(24) == Tenor.of_years(2)``) while genuinely different
durations never collide (``Tenor.of_months(3) != Tenor.of_years(3)``).
Equality and hashing are overridden to use this canonical total-months
identity rather than pydantic's default field-by-field comparison, which
would otherwise treat ``value``/``unit`` pairs expressing the same duration
as distinct. Construction rejects a zero or negative duration - neither is a
representable government-yield or policy-rate maturity.
"""

from __future__ import annotations

from typing import Annotated, Self

from pydantic import Field

from app.core.enums.rates import TenorUnit
from app.core.models.base import DomainModel

_MONTHS_PER_YEAR = 12


class Tenor(DomainModel):
    """A maturity/duration, identified by its canonical total months."""

    value: Annotated[int, Field(gt=0)]
    unit: TenorUnit

    @classmethod
    def of_months(cls, value: int) -> Self:
        return cls(value=value, unit=TenorUnit.MONTHS)

    @classmethod
    def of_years(cls, value: int) -> Self:
        return cls(value=value, unit=TenorUnit.YEARS)

    @property
    def total_months(self) -> int:
        """Canonical duration, in months, independent of construction unit."""
        return self.value * _MONTHS_PER_YEAR if self.unit is TenorUnit.YEARS else self.value

    @property
    def label(self) -> str:
        """Deterministic human-readable label, e.g. ``"3M"``, ``"2Y"``, ``"18M"``.

        Derived from ``total_months`` alone, never from the construction
        unit - ``Tenor.of_months(24).label == Tenor.of_years(2).label ==
        "2Y"``.
        """
        months = self.total_months
        if months % _MONTHS_PER_YEAR == 0:
            return f"{months // _MONTHS_PER_YEAR}Y"
        return f"{months}M"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Tenor):
            return NotImplemented
        return self.total_months == other.total_months

    def __hash__(self) -> int:
        return hash(self.total_months)


__all__ = ["Tenor"]
