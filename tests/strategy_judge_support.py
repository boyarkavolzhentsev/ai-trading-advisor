"""Shared builders for Stage 6B judge tests.

Builds ``TechnicalSupervisorResult``/``ExternalIntelligenceSupervisorResult``
fixtures with precisely controlled dimension/value content (via their own
already-tested support modules), then routes and judges them through the
real ``StrategyRouter``/``Judge`` - never a hand-rolled
``StrategyJudgeResult``. Not a test module itself (no ``test_`` prefix):
pytest will not collect it.
"""

from __future__ import annotations

from app.core.enums.external_intelligence_analysis import ExternalIntelligenceAnalystType, ExternalIntelligenceDimension, ExternalIntelligenceOutcome
from app.core.enums.market import Timeframe
from app.core.enums.quality import FeatureQuality
from app.core.enums.technical_analysis import TechnicalAnalysisDimension, TechnicalAnalystType
from app.core.models.external_intelligence_analysis_result import ExternalIntelligenceAnalysisObservation, ExternalIntelligenceAnalysisResult
from app.core.models.external_intelligence_evidence import ExternalIntelligenceEvidence
from app.core.models.external_intelligence_supervisor_result import ExternalIntelligenceSupervisorResult
from app.core.models.strategy_judge_result import StrategyJudgeResult
from app.core.models.strategy_router_result import StrategyRouterResult
from app.core.models.technical_supervisor_result import TechnicalSupervisorResult
from app.external_intelligence_supervisor.supervisor import ExternalIntelligenceSupervisor
from app.judge.judge import Judge
from app.strategies.router import StrategyRouter
from app.technical_supervisor.supervisor import TechnicalSupervisor
from tests.market_evaluation_support import NOW, SYMBOL, make_context
from tests.strategy_router_support import evaluation
from tests.technical_supervisor_support import DEFAULT_TIMEFRAMES, analyzed_result, make_observation

__all__ = [
    "NOW",
    "SYMBOL",
    "external_with_news_sentiment",
    "make_context",
    "route_and_judge",
    "technical_with_market_structure_break",
    "technical_with_moving_average_corroborator",
    "technical_with_trend_observations",
]


def technical_with_trend_observations(
    *,
    timeframes: tuple[Timeframe, ...] = DEFAULT_TIMEFRAMES[:2],
    return_direction: str | None = "UPWARD",
    slope_direction: str | None = "UPWARD",
) -> TechnicalSupervisorResult:
    """A TREND-analyst-only Technical contour with exact RETURN_DIRECTION/
    SLOPE_DIRECTION values on every given timeframe - ``None`` omits that
    dimension's observation on every timeframe entirely."""
    results = []
    for timeframe in timeframes:
        observations = []
        if return_direction is not None:
            observations.append(make_observation(dimension=TechnicalAnalysisDimension.RETURN_DIRECTION, value=return_direction))
        if slope_direction is not None:
            observations.append(make_observation(dimension=TechnicalAnalysisDimension.SLOPE_DIRECTION, value=slope_direction))
        results.append(analyzed_result(TechnicalAnalystType.TREND, timeframe, observations=tuple(observations)))
    return TechnicalSupervisor().aggregate(tuple(results))


def technical_with_moving_average_corroborator(
    trend_results: tuple, *, price_vs_sma: str, period: str = "20"
) -> TechnicalSupervisorResult:
    """Combines already-built TREND analyst results (as raw
    ``TechnicalAnalysisResult`` tuples, see ``technical_with_trend_observations``'s
    own construction) with a MOVING_AVERAGE analyst on the same timeframes
    reporting one exact ``PRICE_VS_SMA_POSITION`` value."""
    ma_results = [
        analyzed_result(
            TechnicalAnalystType.MOVING_AVERAGE,
            result.timeframe,
            observations=(
                make_observation(dimension=TechnicalAnalysisDimension.PRICE_VS_SMA_POSITION, value=price_vs_sma, subject=period),
            ),
        )
        for result in trend_results
    ]
    return TechnicalSupervisor().aggregate(tuple(trend_results) + tuple(ma_results))


def technical_with_market_structure_break(
    *,
    timeframes: tuple[Timeframe, ...] = DEFAULT_TIMEFRAMES[:2],
    break_confirmed: bool = True,
    break_direction: str | None = "UPWARD_BREAK",
    return_direction: str | None = None,
) -> TechnicalSupervisorResult:
    """A MARKET_STRUCTURE-analyst Technical contour with exact
    STRUCTURAL_BREAK_PRESENCE/LATEST_BREAK_DIRECTION values, optionally
    joined by a TREND analyst reporting an exact RETURN_DIRECTION."""
    results = []
    for timeframe in timeframes:
        observations = [
            make_observation(
                dimension=TechnicalAnalysisDimension.STRUCTURAL_BREAK_PRESENCE,
                value="BREAK_CONFIRMED" if break_confirmed else "NO_BREAK_CONFIRMED",
            )
        ]
        if break_confirmed and break_direction is not None:
            observations.append(
                make_observation(dimension=TechnicalAnalysisDimension.LATEST_BREAK_DIRECTION, value=break_direction)
            )
        results.append(analyzed_result(TechnicalAnalystType.MARKET_STRUCTURE, timeframe, observations=tuple(observations)))
        if return_direction is not None:
            results.append(
                analyzed_result(
                    TechnicalAnalystType.TREND,
                    timeframe,
                    observations=(
                        make_observation(dimension=TechnicalAnalysisDimension.RETURN_DIRECTION, value=return_direction),
                    ),
                )
            )
    return TechnicalSupervisor().aggregate(tuple(results))


def external_with_news_sentiment(
    *, symbol: str = SYMBOL, provider_signs: dict[str, str]
) -> ExternalIntelligenceSupervisorResult:
    """A NEWS_SENTIMENT-only External Intelligence contour with one exact
    per-provider sentiment sign each (``provider_signs`` non-empty), scoped
    to ``symbol``. ``SENTIMENT_PROVIDER_AGREEMENT`` is derived exactly as
    ``NewsSentimentAnalyst`` itself derives it."""
    assert provider_signs, "external_with_news_sentiment requires at least one provider sign"

    evidence = tuple(
        ExternalIntelligenceEvidence(
            feature_name="news_sentiment_observation.sentiment_score",
            observed_value="1",
            reference_value=None,
            quality=FeatureQuality.VALID,
            source_timestamp=NOW,
            source_provider=provider,
            source_record_id=f"{provider}-1",
            source_received_at=NOW,
            provenance=f"test:{provider}",
        )
        for provider in provider_signs
    )
    observations = [
        ExternalIntelligenceAnalysisObservation(
            dimension=ExternalIntelligenceDimension.PER_PROVIDER_SENTIMENT_SIGN,
            value=sign,
            quality=FeatureQuality.VALID,
            subject=provider,
            evidence_refs=(index,),
        )
        for index, (provider, sign) in enumerate(provider_signs.items())
    ]
    # Mirrors NewsSentimentAnalyst.analyze's own agreement derivation exactly.
    unambiguous = [sign for sign in provider_signs.values() if sign != "MIXED"]
    if len(unambiguous) >= 2 and len(set(unambiguous)) == 1:
        agreement = "ALL_AGREE"
    elif len(unambiguous) >= 2:
        agreement = "MIXED"
    else:
        agreement = "INSUFFICIENT_DATA"
    observations.append(
        ExternalIntelligenceAnalysisObservation(
            dimension=ExternalIntelligenceDimension.SENTIMENT_PROVIDER_AGREEMENT,
            value=agreement,
            quality=FeatureQuality.VALID,
            evidence_refs=tuple(range(len(evidence))),
        )
    )

    result = ExternalIntelligenceAnalysisResult(
        analyst_type=ExternalIntelligenceAnalystType.NEWS_SENTIMENT,
        symbol=symbol,
        analysis_time=NOW,
        status=ExternalIntelligenceOutcome.ANALYZED,
        observations=tuple(observations),
        evidence=evidence,
        quality=FeatureQuality.VALID,
    )
    return ExternalIntelligenceSupervisor().aggregate((result,), analysis_time=NOW)


def route_and_judge(**evaluate_kwargs: object) -> tuple[StrategyRouterResult, StrategyJudgeResult]:
    market_evaluation = evaluation(**evaluate_kwargs)
    router_result = StrategyRouter().route(market_evaluation=market_evaluation)
    judge_result = Judge().judge(strategy_router_result=router_result)
    return router_result, judge_result
