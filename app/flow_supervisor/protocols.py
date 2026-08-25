"""Uniform entry point the Stage 2C Flow Supervisor implements.

Mirrors ``app.flow_analysts.protocols.FlowAnalyst``'s call shape one layer
up: a stateless, synchronous, provider-agnostic aggregator over already-
produced Stage 2B results. Takes only the current snapshot's results, no
history argument - matches Stage 2B's own approved decision to defer
cross-snapshot history.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from app.core.models.flow_analysis_result import FlowAnalysisResult
from app.core.models.flow_supervisor_result import FlowSupervisorResult


@runtime_checkable
class FlowSupervisorProtocol(Protocol):
    """Stateless, synchronous, provider-agnostic Stage 2C aggregator."""

    def aggregate(self, results: Sequence[FlowAnalysisResult]) -> FlowSupervisorResult: ...


__all__ = ["FlowSupervisorProtocol"]
