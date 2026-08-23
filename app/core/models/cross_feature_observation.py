"""Deterministic numeric cross-feature co-movement contract.

Deliberately minimal: a plain Pearson correlation coefficient between two
already-computed numeric series drawn from ``FlowFeatureSnapshot`` history,
never a "divergence"/"confirmation"/bullish/bearish label. Interpreting what
a correlation means is the future Flow Supervisor's job, not this layer's.
"""

from __future__ import annotations

from pydantic import Field

from app.core.enums.instrument import ContractType
from app.core.models.analytics_window import AnalyticsWindow
from app.core.models.base import DomainModel, Symbol
from app.core.models.feature_status import FeatureStatus


class CrossFeatureObservation(DomainModel):
    """Pure numeric co-movement statistic between two aligned feature series."""

    symbol: Symbol
    contract_type: ContractType
    window: AnalyticsWindow
    pair_label: str = Field(min_length=1)
    correlation: float | None = None
    sample_count: int = Field(ge=0, default=0)
    status: FeatureStatus
