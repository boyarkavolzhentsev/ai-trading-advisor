"""Stage 4G external-intelligence-supervisor enum - evidence-availability vocabulary only.

``ExternalIntelligenceSupervisorOutcome`` describes whether Stage 4F evidence
*arrived* across the expected analyst-type set, not what it says: a coarse
summary of analyst-type participation
(``app.core.enums.external_intelligence_analysis.ExternalIntelligenceOutcome``
one layer up, aggregated across every expected
``ExternalIntelligenceAnalystType``), never a market-direction or
cross-domain coherence verdict. Mirrors
``app.core.enums.flow_supervisor.FlowSupervisorOutcome`` and
``app.core.enums.technical_supervisor.TechnicalSupervisorOutcome`` one
contour over - deliberately not imported from either, matching the
independence precedent already set between those two modules. See
``app.external_intelligence_supervisor.supervisor`` for the aggregation this
enum's members summarize.
"""

from __future__ import annotations

from enum import StrEnum


class ExternalIntelligenceSupervisorOutcome(StrEnum):
    """Evidence-availability verdict across every expected Stage 4F analyst type."""

    ANALYZED = "ANALYZED"
    PARTIAL = "PARTIAL"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


__all__ = ["ExternalIntelligenceSupervisorOutcome"]
