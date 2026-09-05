"""Decision/Risk Pipeline vocabulary.

Describes only the coarse orchestration outcome of running Stage 5 Market
Evaluation through Stage 9 Session Gate for one cycle - never a trading
recommendation, never a business-policy verdict of its own (every such
verdict remains each stage's own exclusive vocabulary; this enum only
describes how far one cycle's pipeline run got).
"""

from __future__ import annotations

from enum import StrEnum


class DecisionRiskPipelineOutcome(StrEnum):
    """Coarse result of one Decision/Risk Pipeline run.

    ``COMPLETED`` means Stage 5 through Stage 9 all ran - never that any
    family was approved for a trade, position, or execution of any kind; the
    embedded ``StrategySessionResult`` may still show every family blocked.
    ``BLOCKED_BEFORE_RISK`` means Stage 5 through Setup Construction ran, but
    Stage 7 Risk Gate onward did not, because Runtime Fact Assembly could not
    produce a ``READY`` ``AccountRiskSnapshot`` for this cycle.
    """

    COMPLETED = "COMPLETED"
    BLOCKED_BEFORE_RISK = "BLOCKED_BEFORE_RISK"


__all__ = ["DecisionRiskPipelineOutcome"]
