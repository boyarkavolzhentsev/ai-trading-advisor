"""Stage 5A: deterministic Market Evaluation Foundation.

The first layer where Flow Supervisor, Technical Supervisor, and External
Intelligence Supervisor output may be considered together - but only as a
structured, auditable, participation-derived evaluation, never a trade
recommendation. Aggregates already-produced
``FlowSupervisorResult``/``TechnicalSupervisorResult``/
``ExternalIntelligenceSupervisorResult`` objects for one explicit
``MarketEvaluationContext`` into one ``MarketEvaluationResult``:
per-contour participation/quality, a participation-derived top-level
outcome, and structural (identity-only) alignment of External
Intelligence's heterogeneous native scopes against the caller's explicit
context.

Deliberately distinct from ``app.evaluation`` (an existing, unrelated stub
for post-trade review/learning) - this package is never a repurposing of
that one.

Stage 5A performs zero semantic cross-contour comparison: no Flow-vs-
Technical direction/momentum/structure comparison, no news-sentiment-vs-
technical comparison, no macro-vs-price comparison, no on-chain-vs-flow
comparison, no agreement/contradiction/coherence/confluence engine, no
score, no vote, no weight, no confidence, no direction, no recommendation.
Any future cross-contour semantic reconciliation is an entirely separate,
optional, separately-reviewed later layer - never assumed or half-built
here.

Independent from ``app.flow_supervisor``, ``app.technical_supervisor``,
``app.external_intelligence_supervisor`` (their *packages* - Stage 5A only
ever touches their already-produced result *contracts*, which live under
``app.core.models``, and never invokes their ``aggregate()``/``evaluate()``
methods), every Flow/Technical/External analyst or foundation package, and
any Decision/Judge/Strategy/Risk/Portfolio/Execution/LLM layer.
"""

from __future__ import annotations

from app.market_evaluation.errors import (
    FutureContourTimeError,
    MarketEvaluationInputError,
    ScopeMismatchError,
)
from app.market_evaluation.evaluator import MarketEvaluator
from app.market_evaluation.protocols import MarketEvaluationProtocol

__all__ = [
    "FutureContourTimeError",
    "MarketEvaluationInputError",
    "MarketEvaluationProtocol",
    "MarketEvaluator",
    "ScopeMismatchError",
]
