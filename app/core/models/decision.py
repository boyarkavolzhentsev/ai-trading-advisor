"""Trade decision contract."""

from __future__ import annotations

from pydantic import Field

from app.core.enums.trade import TradeDirection
from app.core.models.base import Confidence, DomainModel, Timestamp


class TradeDecision(DomainModel):
    """Aggregated decision of the decision component.

    Produced from assessments plus deterministic risk/money-management input.
    It is an advisory output: execution stays manual in V1.
    """

    direction: TradeDirection
    confidence: Confidence
    reasoning: str = ""
    warnings: list[str] = Field(default_factory=list)
    timestamp: Timestamp
