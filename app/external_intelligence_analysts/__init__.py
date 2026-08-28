"""Stage 4F: deterministic External Intelligence analyst layer.

Consumes Stage 4A-4E factual foundations (``app.macro``, ``app.rates``,
``app.news``, ``app.news_intel``, ``app.onchain``) and produces structured,
evidence-cited, non-directional analytical conclusions - never a trading
decision. Sits exactly where Flow's Stage 2B and Technical's Stage 3B sit
relative to their own foundations, one level below the not-yet-designed
Stage 4G External Intelligence Supervisor.

Four analysts, one shared output family:

1. ``MacroEventAnalyst`` (``app.external_intelligence_analysts.macro_event``)
2. ``RatesYieldAnalyst`` (``app.external_intelligence_analysts.rates_yield``)
3. ``NewsSentimentAnalyst`` (``app.external_intelligence_analysts.news_sentiment``)
4. ``OnChainAnalyst`` (``app.external_intelligence_analysts.on_chain``) - includes
   stablecoin facts; no separate Stablecoin/Liquidity analyst exists, since
   stablecoin facts already share the on-chain ``(asset, network)`` scope.

All four share
``app.core.models.external_intelligence_analysis_result.ExternalIntelligenceAnalysisResult``/
``ExternalIntelligenceAnalysisObservation`` and
``app.core.models.external_intelligence_evidence.ExternalIntelligenceEvidence`` -
no per-analyst Result/Evidence model family, and no free-form
``provenance: dict`` bag on the Result (unlike ``FlowAnalysisResult``/
``TechnicalAnalysisResult``): traceability lives entirely in structured
evidence.

No confidence/strength/evidence-sufficiency score anywhere in this package -
``FeatureQuality`` (``VALID``/``STALE``/``UNAVAILABLE`` only in Stage 4F V1;
``PARTIAL`` remains reserved for a future reviewed rule) is the sole trust
signal, reused unchanged from the rest of the repository.

Every analyst is a pure function of explicit input facts, an explicit
``analysis_time``, and an explicit config - no wall clock, no randomness, no
network call, no LLM call, no hidden windowing (callers select which facts
to supply; no analyst reads a live history/store itself).

Independent from ``app.flow*``, ``app.technical*``, and any future
Stage 4G/Decision/Judge/Execution/Risk layer - see
``tests/test_external_intelligence_analysts_no_flow_coupling.py`` and
``tests/test_external_intelligence_analysts_no_technical_coupling.py``.
"""

from __future__ import annotations

from app.external_intelligence_analysts.config import (
    MacroAnalystConfig,
    NewsSentimentAnalystConfig,
    OnChainAnalystConfig,
    RatesYieldAnalystConfig,
)
from app.external_intelligence_analysts.macro_event import MacroEventAnalyst
from app.external_intelligence_analysts.news_sentiment import NewsSentimentAnalyst
from app.external_intelligence_analysts.on_chain import OnChainAnalyst
from app.external_intelligence_analysts.protocols import (
    MacroEventAnalystProtocol,
    NewsSentimentAnalystProtocol,
    OnChainAnalystProtocol,
    RatesYieldAnalystProtocol,
)
from app.external_intelligence_analysts.rates_yield import RatesYieldAnalyst

__all__ = [
    "MacroAnalystConfig",
    "MacroEventAnalyst",
    "MacroEventAnalystProtocol",
    "NewsSentimentAnalyst",
    "NewsSentimentAnalystConfig",
    "NewsSentimentAnalystProtocol",
    "OnChainAnalyst",
    "OnChainAnalystConfig",
    "OnChainAnalystProtocol",
    "RatesYieldAnalyst",
    "RatesYieldAnalystConfig",
    "RatesYieldAnalystProtocol",
]
