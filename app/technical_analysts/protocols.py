"""Uniform entry point every Stage 3B specialist implements.

Enables a future Stage 3C Technical Supervisor to iterate over all analysts
through one call shape, independent of which domain each one specializes
in. Stage 3B v1 reasons only over one ``TechnicalFeatureSnapshot`` (single
symbol/contract type/timeframe) - the interface therefore takes only the
current snapshot, no history argument and no timeframe-comparison argument.
Mirrors the equivalent Stage 2B analyst protocol one contour over.
"""

from __future__ import annotations

from typing import ClassVar, Protocol, runtime_checkable

from app.core.enums.technical_analysis import TechnicalAnalystType
from app.core.models.technical_analysis_result import TechnicalAnalysisResult
from app.core.models.technical_feature_snapshot import TechnicalFeatureSnapshot


@runtime_checkable
class TechnicalAnalyst(Protocol):
    """Stateless, synchronous, provider-agnostic Stage 3B specialist."""

    analyst_type: ClassVar[TechnicalAnalystType]

    def analyze(self, snapshot: TechnicalFeatureSnapshot) -> TechnicalAnalysisResult: ...


__all__ = ["TechnicalAnalyst"]
