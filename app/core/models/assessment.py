"""Assessment contract emitted by any analytical component."""

from __future__ import annotations

from pydantic import Field

from app.core.enums.trade import TradeDirection
from app.core.models.base import Confidence, DomainModel, Timestamp


class AgentAssessment(DomainModel):
    """Interpretation produced by a single analytical component.

    Used by both LLM agents and deterministic components so a supervisor can
    aggregate heterogeneous inputs through one uniform contract.
    """

    agent_name: str = Field(min_length=1)
    direction: TradeDirection
    confidence: Confidence
    evidence: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    timestamp: Timestamp
