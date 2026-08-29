"""Stage 4G: deterministic External Intelligence Supervisor.

Aggregates already-produced Stage 4F ``ExternalIntelligenceAnalysisResult``
objects (``app.external_intelligence_analysts``) into one
``ExternalIntelligenceSupervisorResult`` per analysis pass: analyst-type
participation, native-scope preservation, quality aggregation, deterministic
canonicalization, and index-based traceability back to the embedded Stage 4F
results. Sits exactly where Flow's Stage 2C and Technical's Stage 3C sit
relative to their own analyst layers.

Stage 4G is participation + scope + quality + traceability only. It performs
no semantic reconciliation: it never reads, interprets, promotes, or
compares any individual ``ExternalIntelligenceDimension`` value (no
``SENTIMENT_PROVIDER_AGREEMENT`` promotion, no contradiction/agreement/
coherence subsystem, no cross-domain mapping or weighting, no score, no
vote, no market interpretation). Every Stage 4F observation remains
reachable only through the unchanged, embedded ``analysis_results`` tuple on
the output model.

No ``TradeDirection``, confidence, strength, weight, or recommendation field
exists anywhere in this package - structurally impossible, mirroring
``app.flow_supervisor``/``app.technical_supervisor``.

Independent from ``app.flow*``, ``app.technical*``, ``app.macro``,
``app.rates``, ``app.news``, ``app.news_intel``, ``app.onchain``, and any
future Evaluation/Decision/Judge/Execution/Risk/Portfolio/LLM layer - see
``tests/test_external_intelligence_supervisor_no_coupling.py``.
"""

from __future__ import annotations

from app.external_intelligence_supervisor.errors import (
    DuplicateAnalystScopeResultError,
    ExternalIntelligenceSupervisorInputError,
    FutureResultTimeError,
)
from app.external_intelligence_supervisor.protocols import ExternalIntelligenceSupervisorProtocol
from app.external_intelligence_supervisor.supervisor import DEFAULT_EXPECTED_ANALYSTS, ExternalIntelligenceSupervisor

__all__ = [
    "DEFAULT_EXPECTED_ANALYSTS",
    "DuplicateAnalystScopeResultError",
    "ExternalIntelligenceSupervisor",
    "ExternalIntelligenceSupervisorInputError",
    "ExternalIntelligenceSupervisorProtocol",
    "FutureResultTimeError",
]
