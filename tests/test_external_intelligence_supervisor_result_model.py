"""Stage 4G ``ExternalIntelligenceSupervisorResult`` model-validator tests.

Constructs the model directly (not via ``aggregate``) to unit-test every
approved invariant in isolation: partition correctness, count correctness,
result-index bounds, scope/outcome/quality matching, and the exact outcome/
overall-quality folds.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.enums.external_intelligence_analysis import ExternalIntelligenceAnalystType, ExternalIntelligenceOutcome
from app.core.enums.external_intelligence_supervisor import ExternalIntelligenceSupervisorOutcome
from app.core.enums.quality import FeatureQuality
from app.core.models.external_intelligence_supervisor_result import (
    ExternalIntelligenceScopeSummary,
    ExternalIntelligenceSupervisorResult,
)
from tests.external_intelligence_supervisor_support import NOW, analyzed_result

MACRO = ExternalIntelligenceAnalystType.MACRO_EVENT


def _base_kwargs() -> dict[str, object]:
    macro_result = analyzed_result(MACRO)
    summary = ExternalIntelligenceScopeSummary(
        analyst_type=MACRO,
        currency=macro_result.currency,
        result_outcome=ExternalIntelligenceOutcome.ANALYZED,
        quality=FeatureQuality.VALID,
        result_index=0,
    )
    return {
        "analysis_time": NOW,
        "outcome": ExternalIntelligenceSupervisorOutcome.ANALYZED,
        "expected_analyst_types": (MACRO,),
        "analyzed_analyst_types": (MACRO,),
        "abstained_analyst_types": (),
        "missing_analyst_types": (),
        "total_input_results": 1,
        "total_analyzed_results": 1,
        "total_abstained_results": 0,
        "overall_quality": FeatureQuality.VALID,
        "scope_summaries": (summary,),
        "analysis_results": (macro_result,),
    }


def test_valid_result_constructs() -> None:
    result = ExternalIntelligenceSupervisorResult(**_base_kwargs())
    assert result.outcome is ExternalIntelligenceSupervisorOutcome.ANALYZED


def test_duplicate_expected_analyst_types_rejected() -> None:
    kwargs = _base_kwargs()
    kwargs["expected_analyst_types"] = (MACRO, MACRO)
    with pytest.raises(ValidationError):
        ExternalIntelligenceSupervisorResult(**kwargs)


def test_analyzed_abstained_missing_must_be_disjoint() -> None:
    kwargs = _base_kwargs()
    kwargs["abstained_analyst_types"] = (MACRO,)  # also in analyzed_analyst_types
    with pytest.raises(ValidationError):
        ExternalIntelligenceSupervisorResult(**kwargs)


def test_partition_must_equal_expected_exactly() -> None:
    kwargs = _base_kwargs()
    kwargs["expected_analyst_types"] = (MACRO, ExternalIntelligenceAnalystType.RATES_YIELD)
    # RATES_YIELD is neither analyzed, abstained, nor missing -> partition incomplete
    with pytest.raises(ValidationError):
        ExternalIntelligenceSupervisorResult(**kwargs)


def test_total_input_results_must_equal_analysis_results_length() -> None:
    kwargs = _base_kwargs()
    kwargs["total_input_results"] = 2
    with pytest.raises(ValidationError):
        ExternalIntelligenceSupervisorResult(**kwargs)


def test_total_input_results_must_equal_scope_summaries_length() -> None:
    kwargs = _base_kwargs()
    kwargs["scope_summaries"] = ()
    with pytest.raises(ValidationError):
        ExternalIntelligenceSupervisorResult(**kwargs)


def test_total_analyzed_results_must_match_scope_summary_count() -> None:
    kwargs = _base_kwargs()
    kwargs["total_analyzed_results"] = 0
    with pytest.raises(ValidationError):
        ExternalIntelligenceSupervisorResult(**kwargs)


def test_total_abstained_results_must_match_scope_summary_count() -> None:
    kwargs = _base_kwargs()
    kwargs["total_abstained_results"] = 1
    with pytest.raises(ValidationError):
        ExternalIntelligenceSupervisorResult(**kwargs)


def test_bad_result_index_rejected() -> None:
    kwargs = _base_kwargs()
    bad_summary = kwargs["scope_summaries"][0].model_copy(update={"result_index": 5})  # type: ignore[index]
    kwargs["scope_summaries"] = (bad_summary,)
    with pytest.raises(ValidationError):
        ExternalIntelligenceSupervisorResult(**kwargs)


def test_mismatched_scope_rejected() -> None:
    kwargs = _base_kwargs()
    bad_summary = kwargs["scope_summaries"][0].model_copy(update={"currency": "EUR"})  # type: ignore[index]
    kwargs["scope_summaries"] = (bad_summary,)
    with pytest.raises(ValidationError):
        ExternalIntelligenceSupervisorResult(**kwargs)


def test_mismatched_result_outcome_rejected() -> None:
    kwargs = _base_kwargs()
    bad_summary = kwargs["scope_summaries"][0].model_copy(  # type: ignore[index]
        update={"result_outcome": ExternalIntelligenceOutcome.ABSTAINED}
    )
    kwargs["scope_summaries"] = (bad_summary,)
    kwargs["total_analyzed_results"] = 0
    kwargs["total_abstained_results"] = 1
    with pytest.raises(ValidationError):
        ExternalIntelligenceSupervisorResult(**kwargs)


def test_mismatched_quality_rejected() -> None:
    kwargs = _base_kwargs()
    bad_summary = kwargs["scope_summaries"][0].model_copy(update={"quality": FeatureQuality.STALE})  # type: ignore[index]
    kwargs["scope_summaries"] = (bad_summary,)
    with pytest.raises(ValidationError):
        ExternalIntelligenceSupervisorResult(**kwargs)


def test_wrong_outcome_rejected() -> None:
    kwargs = _base_kwargs()
    kwargs["outcome"] = ExternalIntelligenceSupervisorOutcome.PARTIAL
    with pytest.raises(ValidationError):
        ExternalIntelligenceSupervisorResult(**kwargs)


def test_wrong_overall_quality_rejected() -> None:
    kwargs = _base_kwargs()
    kwargs["overall_quality"] = FeatureQuality.STALE
    with pytest.raises(ValidationError):
        ExternalIntelligenceSupervisorResult(**kwargs)


def test_result_is_frozen() -> None:
    result = ExternalIntelligenceSupervisorResult(**_base_kwargs())
    with pytest.raises(ValidationError):
        result.outcome = ExternalIntelligenceSupervisorOutcome.PARTIAL  # type: ignore[misc]


def test_result_forbids_unknown_fields() -> None:
    kwargs = _base_kwargs()
    kwargs["unexpected_field"] = "value"
    with pytest.raises(ValidationError):
        ExternalIntelligenceSupervisorResult(**kwargs)


def test_result_has_no_provenance_field() -> None:
    assert "provenance" not in ExternalIntelligenceSupervisorResult.model_fields
