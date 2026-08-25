"""Stage 2C flow-supervisor enum - evidence-availability vocabulary only.

``FlowSupervisorOutcome`` describes whether Stage 2B evidence *arrived*, not
what it says: it is a coarse summary of analyst participation
(``app.core.enums.flow_analysis.AnalystOutcome`` one layer up, aggregated
across every expected analyst), never a market-direction or
market-coherence verdict. See ``app.flow_supervisor.supervisor`` for the
aggregation this enum's members summarize.
"""

from __future__ import annotations

from enum import StrEnum


class FlowSupervisorOutcome(StrEnum):
    """Evidence-availability verdict across all expected Stage 2B analysts."""

    ANALYZED = "ANALYZED"
    PARTIAL = "PARTIAL"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


__all__ = ["FlowSupervisorOutcome"]
