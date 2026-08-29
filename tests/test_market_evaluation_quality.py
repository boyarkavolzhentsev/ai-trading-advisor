"""Stage 5A quality-aggregation tests.

``overall_quality`` folds only ``ANALYZED``/``PARTIAL`` contours; ``MISSING``
and ``INSUFFICIENT_EVIDENCE`` contours are excluded. External alignment
relevance never alters ``external_quality`` or ``overall_quality``.
"""

from __future__ import annotations

from functools import partial

from app.core.enums.external_intelligence_analysis import ExternalIntelligenceAnalystType
from app.core.enums.flow_analysis import AnalystType as FlowAnalystType
from app.core.enums.quality import FeatureQuality
from app.flow_supervisor.supervisor import FlowSupervisor
from app.market_evaluation.evaluator import MarketEvaluator
from tests.external_intelligence_supervisor_support import analyzed_result as _base_ext_analyzed_result
from tests.flow_supervisor_support import analyzed_result as flow_analyzed_result
from tests.market_evaluation_support import (
    NOW,
    OTHER_SYMBOL,
    SYMBOL,
    external_result_with_scopes,
    full_external_result,
    full_flow_result,
    full_technical_result,
    insufficient_flow_result,
    insufficient_technical_result,
    make_context,
)

ext_analyzed_result = partial(_base_ext_analyzed_result, analysis_time=NOW)


def _evaluate(**kwargs):
    kwargs.setdefault("flow", None)
    kwargs.setdefault("technical", None)
    kwargs.setdefault("external", None)
    kwargs.setdefault("context", make_context())
    kwargs.setdefault("evaluation_time", NOW)
    return MarketEvaluator().evaluate(**kwargs)


def test_overall_quality_valid_when_all_analyzed_valid() -> None:
    result = _evaluate(flow=full_flow_result(), technical=full_technical_result(), external=full_external_result())
    assert result.flow_quality is FeatureQuality.VALID
    assert result.technical_quality is FeatureQuality.VALID
    assert result.external_quality is FeatureQuality.VALID
    assert result.overall_quality is FeatureQuality.VALID


def test_overall_quality_stale_when_one_contour_stale() -> None:
    stale_flow = FlowSupervisor().aggregate(
        (flow_analyzed_result(FlowAnalystType.TAKER_FLOW, quality=FeatureQuality.STALE),)
    )
    result = _evaluate(flow=stale_flow, technical=full_technical_result())
    assert result.overall_quality is FeatureQuality.STALE


def test_overall_quality_partial_contour_still_folded() -> None:
    partial_flow_with_valid = FlowSupervisor().aggregate(
        (flow_analyzed_result(FlowAnalystType.TAKER_FLOW, quality=FeatureQuality.VALID),)
    )
    result = _evaluate(flow=partial_flow_with_valid)
    assert result.flow_status.value == "PARTIAL"
    assert result.overall_quality is FeatureQuality.VALID


def test_overall_quality_unavailable_when_no_qualifying_contours() -> None:
    result = _evaluate()
    assert result.overall_quality is FeatureQuality.UNAVAILABLE


def test_missing_contour_excluded_from_quality_fold() -> None:
    result = _evaluate(flow=full_flow_result())
    assert result.technical_quality is None
    assert result.external_quality is None
    assert result.overall_quality is FeatureQuality.VALID


def test_insufficient_evidence_excluded_from_quality_fold() -> None:
    result = _evaluate(flow=full_flow_result(), technical=insufficient_technical_result())
    # insufficient_technical_result's own quality is UNAVAILABLE (structurally,
    # per TechnicalSupervisorResult's own quality rule) - it must not poison
    # an otherwise-VALID overall fold.
    assert result.technical_quality is FeatureQuality.UNAVAILABLE
    assert result.overall_quality is FeatureQuality.VALID


def test_external_alignment_does_not_alter_external_quality() -> None:
    external = external_result_with_scopes(
        (ext_analyzed_result(ExternalIntelligenceAnalystType.NEWS_SENTIMENT, symbol=OTHER_SYMBOL, quality=FeatureQuality.VALID),)
    )
    context = make_context(symbol=SYMBOL)  # does not match the NEWS_SENTIMENT scope's symbol
    result = _evaluate(external=external, context=context)
    assert result.external_quality is FeatureQuality.VALID
    assert result.external.overall_quality is FeatureQuality.VALID


def test_external_alignment_does_not_alter_overall_quality() -> None:
    external = external_result_with_scopes(
        (ext_analyzed_result(ExternalIntelligenceAnalystType.NEWS_SENTIMENT, symbol=OTHER_SYMBOL, quality=FeatureQuality.VALID),)
    )
    context = make_context(symbol=SYMBOL)
    result = _evaluate(external=external, context=context)
    assert result.overall_quality is FeatureQuality.VALID
