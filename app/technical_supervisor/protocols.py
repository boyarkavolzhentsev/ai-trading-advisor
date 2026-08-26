"""Uniform entry point the Stage 3C Technical Supervisor implements.

Mirrors ``app.technical_analysts.protocols.TechnicalAnalyst``'s call shape
one layer up: a stateless, synchronous, provider-agnostic aggregator over
already-produced Stage 3B results. Takes only the current evaluation's
results, no history argument - matches Stage 3B's own approved decision to
defer cross-evaluation history.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from app.core.models.technical_analysis_result import TechnicalAnalysisResult
from app.core.models.technical_supervisor_result import TechnicalSupervisorResult


@runtime_checkable
class TechnicalSupervisorProtocol(Protocol):
    """Stateless, synchronous, provider-agnostic Stage 3C aggregator."""

    def aggregate(self, results: Sequence[TechnicalAnalysisResult]) -> TechnicalSupervisorResult: ...


__all__ = ["TechnicalSupervisorProtocol"]
