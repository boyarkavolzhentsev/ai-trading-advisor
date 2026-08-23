"""Per-feature-block data quality verdict contract.

Attached to every windowed/point feature block produced under ``app.flow`` so
a consumer never has to guess whether a number is trustworthy - mirrors
``DataQuality``'s "verdict object built when asked" posture, but one layer up
and with the finer ``FeatureQuality`` vocabulary a derived feature needs.
"""

from __future__ import annotations

from pydantic import Field

from app.core.enums.quality import FeatureQuality
from app.core.models.base import DomainModel


class FeatureStatus(DomainModel):
    """Verdict of a Stage 2A calculator about one computed feature block."""

    quality: FeatureQuality
    sample_count: int = Field(ge=0, default=0)
    reasons: list[str] = Field(default_factory=list)
