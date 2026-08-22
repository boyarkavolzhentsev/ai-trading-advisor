"""Data quality contract produced by validator components."""

from __future__ import annotations

from pydantic import Field

from app.core.models.base import DomainModel, Timestamp


class DataQuality(DomainModel):
    """Verdict of a validator about a piece of market data.

    Attached to every snapshot so downstream components can degrade instead of
    trusting unverified data.
    """

    is_valid: bool
    is_stale: bool = False
    missing_data: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source: str = Field(min_length=1)
    checked_at: Timestamp
