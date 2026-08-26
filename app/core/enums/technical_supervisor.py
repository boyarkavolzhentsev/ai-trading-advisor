"""Stage 3C technical-supervisor enum - evidence-availability vocabulary only.

``TechnicalSupervisorOutcome`` describes whether Stage 3B evidence *arrived*
across the full expected analyst x timeframe matrix, not what it says: a
coarse summary of cell participation
(``app.core.enums.technical_analysis.TechnicalAnalystOutcome`` one layer up,
aggregated across every expected ``(analyst_type, timeframe)`` cell), never a
market-direction or cross-timeframe coherence verdict. Deliberately
independent of ``app.core.enums.flow_supervisor.FlowSupervisorOutcome`` - the
identical 3-state shape one contour over is not a shared dependency,
mirroring the precedent already set between Stage 3B's and Stage 2B's own
enum modules. See ``app.technical_supervisor.supervisor`` for the
aggregation this enum's members summarize.
"""

from __future__ import annotations

from enum import StrEnum


class TechnicalSupervisorOutcome(StrEnum):
    """Evidence-availability verdict across every expected (analyst, timeframe) cell."""

    ANALYZED = "ANALYZED"
    PARTIAL = "PARTIAL"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


__all__ = ["TechnicalSupervisorOutcome"]
