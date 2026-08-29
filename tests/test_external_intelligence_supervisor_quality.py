"""Stage 4G quality-aggregation tests.

Per-scope quality is copied verbatim from the underlying Stage 4F result.
Overall quality is ``worse_of_many`` over ANALYZED results only - ABSTAINED
results (structurally always ``UNAVAILABLE``, see
``ExternalIntelligenceAnalysisResult._validate_abstention_consistency``)
never enter the fold.
"""

from __future__ import annotations

from app.core.enums.external_intelligence_analysis import ExternalIntelligenceAnalystType
from app.core.enums.quality import FeatureQuality
from app.external_intelligence_supervisor.supervisor import ExternalIntelligenceSupervisor
from tests.external_intelligence_supervisor_support import NOW, abstained_result, analyzed_result


def test_per_scope_quality_is_copied_exactly() -> None:
    result = ExternalIntelligenceSupervisor().aggregate(
        (analyzed_result(ExternalIntelligenceAnalystType.MACRO_EVENT, quality=FeatureQuality.STALE),),
        analysis_time=NOW,
    )
    assert result.scope_summaries[0].quality is FeatureQuality.STALE


def test_overall_quality_from_analyzed_results_only_all_valid() -> None:
    results = (
        analyzed_result(ExternalIntelligenceAnalystType.MACRO_EVENT, quality=FeatureQuality.VALID),
        analyzed_result(ExternalIntelligenceAnalystType.NEWS_SENTIMENT, quality=FeatureQuality.VALID),
    )
    result = ExternalIntelligenceSupervisor().aggregate(results, analysis_time=NOW)
    assert result.overall_quality is FeatureQuality.VALID


def test_valid_and_stale_analyzed_yields_stale() -> None:
    results = (
        analyzed_result(ExternalIntelligenceAnalystType.MACRO_EVENT, quality=FeatureQuality.VALID),
        analyzed_result(ExternalIntelligenceAnalystType.NEWS_SENTIMENT, quality=FeatureQuality.STALE),
    )
    result = ExternalIntelligenceSupervisor().aggregate(results, analysis_time=NOW)
    assert result.overall_quality is FeatureQuality.STALE


def test_abstained_unavailable_does_not_poison_valid_analyzed_quality() -> None:
    results = (
        analyzed_result(ExternalIntelligenceAnalystType.MACRO_EVENT, quality=FeatureQuality.VALID),
        abstained_result(ExternalIntelligenceAnalystType.RATES_YIELD),
        abstained_result(ExternalIntelligenceAnalystType.ON_CHAIN),
        abstained_result(ExternalIntelligenceAnalystType.NEWS_SENTIMENT),
    )
    result = ExternalIntelligenceSupervisor().aggregate(results, analysis_time=NOW)
    assert result.overall_quality is FeatureQuality.VALID


def test_zero_analyzed_yields_unavailable() -> None:
    results = tuple(abstained_result(t) for t in ExternalIntelligenceAnalystType)
    result = ExternalIntelligenceSupervisor().aggregate(results, analysis_time=NOW)
    assert result.overall_quality is FeatureQuality.UNAVAILABLE


def test_empty_input_yields_unavailable_overall_quality() -> None:
    result = ExternalIntelligenceSupervisor().aggregate((), analysis_time=NOW)
    assert result.overall_quality is FeatureQuality.UNAVAILABLE


def test_no_confidence_or_score_field_exists() -> None:
    from app.core.models.external_intelligence_supervisor_result import ExternalIntelligenceSupervisorResult

    forbidden = {"confidence", "strength", "score", "evidence_sufficiency"}
    assert forbidden.isdisjoint(ExternalIntelligenceSupervisorResult.model_fields)
