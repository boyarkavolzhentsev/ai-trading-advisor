"""Uniform entry point the Stage 4G External Intelligence Supervisor implements.

Mirrors ``app.flow_supervisor.protocols.FlowSupervisorProtocol``/
``app.technical_supervisor.protocols.TechnicalSupervisorProtocol`` one
contour over: a stateless, synchronous, provider-agnostic aggregator over
already-produced Stage 4F results. Takes only the current pass's results
plus an explicit ``analysis_time`` - no history argument, no storage, no
network/provider methods.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from app.core.models.base import Timestamp
from app.core.models.external_intelligence_analysis_result import ExternalIntelligenceAnalysisResult
from app.core.models.external_intelligence_supervisor_result import ExternalIntelligenceSupervisorResult


@runtime_checkable
class ExternalIntelligenceSupervisorProtocol(Protocol):
    """Stateless, synchronous, provider-agnostic Stage 4G aggregator."""

    def aggregate(
        self,
        results: Sequence[ExternalIntelligenceAnalysisResult],
        *,
        analysis_time: Timestamp,
    ) -> ExternalIntelligenceSupervisorResult: ...


__all__ = ["ExternalIntelligenceSupervisorProtocol"]
