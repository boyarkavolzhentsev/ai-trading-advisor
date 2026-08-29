"""Stage 5A end-to-end traceability tests.

MarketEvaluationResult.{flow,technical,external} embed the supplied
supervisor results unchanged. For matched External scopes:
ExternalScopeAlignmentRef.scope_summary_index -> external.scope_summaries[i]
-> Stage 4G result_index -> external.analysis_results[result_index] ->
Stage 4F observations -> evidence_refs -> ExternalIntelligenceEvidence ->
Stage 4A-4E provenance. No evidence copying at any hop.
"""

from __future__ import annotations

from functools import partial

from app.core.enums.external_intelligence_analysis import ExternalIntelligenceAnalystType
from app.core.models.market_evaluation_result import MarketEvaluationResult
from app.market_evaluation.evaluator import MarketEvaluator
from tests.external_intelligence_supervisor_support import analyzed_result as _base_ext_analyzed_result
from tests.market_evaluation_support import (
    NOW,
    SYMBOL,
    external_result_with_scopes,
    full_external_result,
    full_flow_result,
    full_technical_result,
    make_context,
)

ext_analyzed_result = partial(_base_ext_analyzed_result, analysis_time=NOW)


def test_embedded_supervisors_are_the_supplied_objects() -> None:
    flow = full_flow_result()
    technical = full_technical_result()
    external = full_external_result()
    result = MarketEvaluator().evaluate(
        flow=flow, technical=technical, external=external, context=make_context(), evaluation_time=NOW
    )
    assert result.flow is flow
    assert result.technical is technical
    assert result.external is external


def test_full_external_traceability_chain() -> None:
    external = external_result_with_scopes(
        (ext_analyzed_result(ExternalIntelligenceAnalystType.NEWS_SENTIMENT, symbol=SYMBOL),)
    )
    result = MarketEvaluator().evaluate(
        flow=None, technical=None, external=external, context=make_context(symbol=SYMBOL), evaluation_time=NOW
    )
    assert len(result.external_scope_alignment) == 1
    ref = result.external_scope_alignment[0]

    scope_summary = result.external.scope_summaries[ref.scope_summary_index]
    stage_4f_result = result.external.analysis_results[scope_summary.result_index]
    assert stage_4f_result.analyst_type is ExternalIntelligenceAnalystType.NEWS_SENTIMENT

    for observation in stage_4f_result.observations:
        for evidence_idx in observation.evidence_refs:
            evidence = stage_4f_result.evidence[evidence_idx]
            assert evidence.provenance
            assert evidence.source_provider


def test_no_copied_evidence_on_result_model() -> None:
    assert "evidence" not in MarketEvaluationResult.model_fields
    assert "evidence_refs" not in MarketEvaluationResult.model_fields


def test_no_market_evaluation_evidence_model_exists() -> None:
    import app.core.models.market_evaluation_result as module

    assert not hasattr(module, "MarketEvaluationEvidence")


def test_serialization_round_trip_preserves_traceability() -> None:
    flow = full_flow_result()
    technical = full_technical_result()
    external = full_external_result()
    result = MarketEvaluator().evaluate(
        flow=flow, technical=technical, external=external, context=make_context(), evaluation_time=NOW
    )

    payload = result.model_dump_json()
    restored = MarketEvaluationResult.model_validate_json(payload)

    assert restored == result
    for ref in restored.external_scope_alignment:
        assert restored.external.scope_summaries[ref.scope_summary_index] is not None
