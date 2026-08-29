"""Stage 4G end-to-end traceability tests.

ExternalIntelligenceScopeSummary.result_index -> analysis_results[i] ->
observations -> evidence_refs -> ExternalIntelligenceEvidence -> Stage
4A-4E provenance. No Stage 4G evidence-copy model exists; every hop is a
plain index into the embedded, unchanged Stage 4F result.
"""

from __future__ import annotations

from app.core.enums.external_intelligence_analysis import ExternalIntelligenceAnalystType
from app.core.models.external_intelligence_supervisor_result import ExternalIntelligenceSupervisorResult
from app.external_intelligence_supervisor.supervisor import ExternalIntelligenceSupervisor
from tests.external_intelligence_supervisor_support import NOW, analyzed_result, full_analyzed_set


def test_every_result_index_resolves() -> None:
    result = ExternalIntelligenceSupervisor().aggregate(full_analyzed_set(), analysis_time=NOW)
    for summary in result.scope_summaries:
        assert 0 <= summary.result_index < len(result.analysis_results)


def test_scope_summary_exactly_matches_referenced_result() -> None:
    result = ExternalIntelligenceSupervisor().aggregate(full_analyzed_set(), analysis_time=NOW)
    for summary in result.scope_summaries:
        referenced = result.analysis_results[summary.result_index]
        assert summary.analyst_type is referenced.analyst_type
        assert summary.currency == referenced.currency
        assert summary.symbol == referenced.symbol
        assert summary.asset == referenced.asset
        assert summary.network == referenced.network
        assert summary.result_outcome is referenced.status
        assert summary.quality is referenced.quality


def test_stage_4f_evidence_remains_reachable_through_embedded_result() -> None:
    original = analyzed_result(ExternalIntelligenceAnalystType.MACRO_EVENT)
    result = ExternalIntelligenceSupervisor().aggregate((original,), analysis_time=NOW)

    summary = result.scope_summaries[0]
    referenced = result.analysis_results[summary.result_index]
    assert referenced == original

    for observation in referenced.observations:
        for evidence_idx in observation.evidence_refs:
            evidence = referenced.evidence[evidence_idx]
            assert evidence.provenance
            assert evidence.source_provider


def test_embedded_results_are_unchanged_from_input() -> None:
    original = full_analyzed_set()
    result = ExternalIntelligenceSupervisor().aggregate(original, analysis_time=NOW)
    embedded_by_type = {r.analyst_type: r for r in result.analysis_results}
    for source in original:
        assert embedded_by_type[source.analyst_type] == source


def test_no_stage_4g_evidence_copy_model_exists() -> None:
    assert "evidence" not in ExternalIntelligenceSupervisorResult.model_fields
    assert "evidence_refs" not in ExternalIntelligenceSupervisorResult.model_fields


def test_serialization_round_trip_preserves_traceability() -> None:
    result = ExternalIntelligenceSupervisor().aggregate(full_analyzed_set(), analysis_time=NOW)

    payload = result.model_dump_json()
    restored = ExternalIntelligenceSupervisorResult.model_validate_json(payload)

    assert restored == result
    for summary in restored.scope_summaries:
        assert restored.analysis_results[summary.result_index] is not None
