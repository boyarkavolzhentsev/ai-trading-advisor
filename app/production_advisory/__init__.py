"""Stage 0D Production Advisory Composition.

The one process-level coordinator wiring Flow/Technical production
composition (Stage 0A/0B), the MQL5 calendar bridge, and the deterministic
runtime-cycle orchestrator (``app.orchestration.runtime_cycle.
run_runtime_cycle``) together for one fixed, operator-configured V1 symbol.
Composition only - no new trading/decision logic lives here.
"""

from __future__ import annotations

from app.production_advisory.composer import ProductionAdvisoryComposer
from app.production_advisory.config import ProductionAdvisoryConfig
from app.production_advisory.errors import ProductionAdvisoryDuplicateCycleError, ProductionAdvisoryError
from app.production_advisory.result import ProductionAdvisoryCycleOutcome, ProductionAdvisoryCycleResult

__all__ = [
    "ProductionAdvisoryComposer",
    "ProductionAdvisoryConfig",
    "ProductionAdvisoryCycleOutcome",
    "ProductionAdvisoryCycleResult",
    "ProductionAdvisoryDuplicateCycleError",
    "ProductionAdvisoryError",
]
