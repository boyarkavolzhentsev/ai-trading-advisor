"""Shared builders for Stage 6A strategy-router tests.

Builds ``MarketEvaluationResult`` fixtures via the real Stage 5A
``MarketEvaluator`` over real Stage 2C/3C/4G supervisor results (reusing
``tests/market_evaluation_support.py`` and its own upstream support
modules), for the specific participation/quality/alignment combinations
Stage 6A's structural rules need - never a hand-rolled
``MarketEvaluationResult``. Not a test module itself (no ``test_`` prefix):
pytest will not collect it.
"""

from __future__ import annotations

from app.core.enums.external_intelligence_analysis import ExternalIntelligenceAnalystType
from app.core.enums.flow_analysis import AnalystType as FlowAnalystType
from app.core.enums.quality import FeatureQuality
from app.core.enums.technical_analysis import TechnicalAnalystType
from app.core.models.external_intelligence_supervisor_result import ExternalIntelligenceSupervisorResult
from app.core.models.flow_supervisor_result import FlowSupervisorResult
from app.core.models.market_evaluation_context import MarketEvaluationContext
from app.core.models.market_evaluation_result import MarketEvaluationResult
from app.core.models.technical_supervisor_result import TechnicalSupervisorResult
from app.external_intelligence_supervisor.supervisor import ExternalIntelligenceSupervisor
from app.flow_supervisor.supervisor import FlowSupervisor
from app.market_evaluation.evaluator import MarketEvaluator
from app.technical_supervisor.supervisor import TechnicalSupervisor
from tests.external_intelligence_supervisor_support import analyzed_result as _ext_analyzed_result
from tests.flow_supervisor_support import analyzed_result as _flow_analyzed_result
from tests.market_evaluation_support import NOW, OTHER_SYMBOL, SYMBOL, make_context
from tests.technical_supervisor_support import DEFAULT_TIMEFRAMES as _TECHNICAL_DEFAULT_TIMEFRAMES
from tests.technical_supervisor_support import analyzed_result as _technical_analyzed_result

__all__ = [
    "NOW",
    "SYMBOL",
    "evaluation",
    "external_result_matched",
    "external_result_unmatched",
    "external_result_with_quality",
    "flow_result_with_quality",
    "make_context",
    "technical_result_with_quality",
]


def flow_result_with_quality(quality: FeatureQuality) -> FlowSupervisorResult:
    """A one-analyst (``PARTIAL``) Flow contour carrying the given quality."""
    return FlowSupervisor().aggregate((_flow_analyzed_result(FlowAnalystType.TAKER_FLOW, quality=quality),))


def technical_result_with_quality(quality: FeatureQuality) -> TechnicalSupervisorResult:
    """A one-cell (``PARTIAL``) Technical contour carrying the given quality."""
    return TechnicalSupervisor().aggregate(
        (_technical_analyzed_result(TechnicalAnalystType.TREND, _TECHNICAL_DEFAULT_TIMEFRAMES[0], quality=quality),)
    )


def external_result_with_quality(quality: FeatureQuality) -> ExternalIntelligenceSupervisorResult:
    """A one-analyst (``PARTIAL``) External Intelligence contour, scoped to
    ``CURRENCY`` (MACRO_EVENT's default native scope - deliberately not
    aligned to any ``MarketEvaluationContext`` field), carrying the given
    quality."""
    return ExternalIntelligenceSupervisor().aggregate(
        (_ext_analyzed_result(ExternalIntelligenceAnalystType.MACRO_EVENT, analysis_time=NOW, quality=quality),),
        analysis_time=NOW,
    )


def external_result_matched(*, symbol: str = SYMBOL) -> ExternalIntelligenceSupervisorResult:
    """An External Intelligence contour with one NEWS_SENTIMENT scope whose
    ``symbol`` matches ``symbol`` - aligns to a ``MarketEvaluationContext``
    built with the same ``symbol``."""
    return ExternalIntelligenceSupervisor().aggregate(
        (_ext_analyzed_result(ExternalIntelligenceAnalystType.NEWS_SENTIMENT, analysis_time=NOW, symbol=symbol),),
        analysis_time=NOW,
    )


def external_result_unmatched() -> ExternalIntelligenceSupervisorResult:
    """An External Intelligence contour with one NEWS_SENTIMENT scope whose
    ``symbol`` (``OTHER_SYMBOL``) deliberately never matches a
    ``MarketEvaluationContext`` built with the default ``SYMBOL`` -
    structurally present, but ``NO_MATCHING_SCOPE``."""
    return ExternalIntelligenceSupervisor().aggregate(
        (_ext_analyzed_result(ExternalIntelligenceAnalystType.NEWS_SENTIMENT, analysis_time=NOW, symbol=OTHER_SYMBOL),),
        analysis_time=NOW,
    )


def evaluation(
    *,
    flow: FlowSupervisorResult | None = None,
    technical: TechnicalSupervisorResult | None = None,
    external: ExternalIntelligenceSupervisorResult | None = None,
    context: MarketEvaluationContext | None = None,
) -> MarketEvaluationResult:
    return MarketEvaluator().evaluate(
        flow=flow,
        technical=technical,
        external=external,
        context=context if context is not None else make_context(),
        evaluation_time=NOW,
    )
