"""Shared model bases and reusable constrained field types.

Money-like values use ``Decimal`` (never ``float``) because all future
financial arithmetic is deterministic and must be exact. Dimensionless scores
and ratios stay ``float``.

All timestamps are timezone-aware; naive datetimes are rejected so that broker
server time, exchange time and local time can never be silently mixed.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class DomainModel(BaseModel):
    """Immutable, strictly validated value object.

    Frozen by default: contracts are produced once and passed between
    components without being mutated in place.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        str_strip_whitespace=True,
    )


class MutableDomainModel(BaseModel):
    """Record whose fields are updated over its lifecycle.

    Used only where an external tracker (e.g. the future MT5 read-only tracker)
    fills in values as they become known. Assignments are re-validated.
    """

    model_config = ConfigDict(
        frozen=False,
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
    )


Timestamp = AwareDatetime
"""Timezone-aware point in time."""

Confidence = Annotated[float, Field(ge=0.0, le=1.0)]
"""Confidence score in the closed interval [0, 1]."""

Percent = Annotated[Decimal, Field(ge=0, le=100)]
"""Percentage value in [0, 100] (1.5 means 1.5%)."""

Price = Annotated[Decimal, Field(ge=0)]
"""Non-negative instrument price."""

Volume = Annotated[Decimal, Field(ge=0)]
"""Non-negative traded volume."""

Money = Annotated[Decimal, Field(ge=0)]
"""Non-negative monetary amount in account currency."""

Ratio = Annotated[float, Field(ge=0.0)]
"""Non-negative dimensionless ratio (e.g. risk/reward, profit factor)."""

Symbol = Annotated[str, Field(min_length=1, max_length=32)]
"""Instrument identifier as reported by the data source."""

__all__ = [
    "Confidence",
    "DomainModel",
    "Money",
    "MutableDomainModel",
    "Percent",
    "Price",
    "Ratio",
    "Symbol",
    "Timestamp",
    "Volume",
]
