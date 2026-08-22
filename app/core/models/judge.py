"""Judge verdict contract."""

from __future__ import annotations

from pydantic import Field

from app.core.enums.judge import JudgeVerdictType
from app.core.models.base import Confidence, DomainModel, Timestamp


class JudgeVerdict(DomainModel):
    """Independent final review of a decision.

    The judge only reviews the decision and its supporting material; it does
    not redo market analysis and does not produce a direction of its own.
    """

    verdict: JudgeVerdictType
    confidence: Confidence
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    timestamp: Timestamp
