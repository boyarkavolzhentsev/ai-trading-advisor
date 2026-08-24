"""Uniform entry point every Stage 2B specialist implements.

Enables a future Stage 2C Flow Supervisor to iterate over all analysts
through one call shape, independent of which domain each one specializes
in. Stage 2B v1 reasons only across the windows already contained in one
``FlowFeatureSnapshot`` (see the Stage 2B design report's approved decision
to defer cross-snapshot history) - the interface therefore takes only the
current snapshot, no history argument.
"""

from __future__ import annotations

from typing import ClassVar, Protocol, runtime_checkable

from app.core.enums.flow_analysis import AnalystType
from app.core.models.flow_analysis_result import FlowAnalysisResult
from app.core.models.flow_feature_snapshot import FlowFeatureSnapshot


@runtime_checkable
class FlowAnalyst(Protocol):
    """Stateless, synchronous, provider-agnostic Stage 2B specialist."""

    analyst_type: ClassVar[AnalystType]

    def analyze(self, snapshot: FlowFeatureSnapshot) -> FlowAnalysisResult: ...


__all__ = ["FlowAnalyst"]
