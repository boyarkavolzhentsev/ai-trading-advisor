"""Risk assessment contract."""

from __future__ import annotations

from pydantic import Field

from app.core.models.base import DomainModel, Money, Percent


class RiskAssessment(DomainModel):
    """Verdict of the risk component about a proposed setup.

    ``risk_percent`` is a percentage of account equity in [0, 100];
    ``max_loss`` is the corresponding worst-case amount in account currency.
    Both are supplied by a deterministic calculator, never by an LLM.
    """

    approved: bool
    risk_percent: Percent
    max_loss: Money
    reason: str = ""
    warnings: list[str] = Field(default_factory=list)
