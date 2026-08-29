"""Stage 5A ``MarketEvaluationResult`` model-validator tests.

Constructs the model directly (not via ``MarketEvaluator.evaluate``) to
unit-test every approved invariant in isolation: contour status/quality
must match the embedded contour, the outcome truth table, the quality fold,
external-alignment-status consistency, alignment-index bounds, and
matched_by/native-scope consistency.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.enums.market_evaluation import (
    ExternalAlignmentStatus,
    ExternalScopeMatchKind,
    MarketEvaluationContourStatus,
    MarketEvaluationOutcome,
)
from app.core.enums.quality import FeatureQuality
from app.core.models.market_evaluation_result import ExternalScopeAlignmentRef, MarketEvaluationResult
from tests.market_evaluation_support import NOW, full_flow_result, make_context


def _base_kwargs() -> dict[str, object]:
    flow = full_flow_result()
    return {
        "evaluation_time": NOW,
        "context": make_context(),
        "outcome": MarketEvaluationOutcome.PARTIAL,
        "flow_status": MarketEvaluationContourStatus.ANALYZED,
        "technical_status": MarketEvaluationContourStatus.MISSING,
        "external_status": MarketEvaluationContourStatus.MISSING,
        "flow_quality": FeatureQuality.VALID,
        "technical_quality": None,
        "external_quality": None,
        "overall_quality": FeatureQuality.VALID,
        "flow": flow,
        "technical": None,
        "external": None,
        "external_alignment_status": ExternalAlignmentStatus.MISSING,
        "external_scope_alignment": (),
    }


def test_valid_result_constructs() -> None:
    result = MarketEvaluationResult(**_base_kwargs())
    assert result.outcome is MarketEvaluationOutcome.PARTIAL


# --- A. contour status/quality must match embedded contour ---


def test_flow_status_must_be_missing_when_flow_is_none() -> None:
    kwargs = _base_kwargs()
    kwargs["flow"] = None
    # flow_status still ANALYZED -> inconsistent
    with pytest.raises(ValidationError):
        MarketEvaluationResult(**kwargs)


def test_flow_quality_must_be_none_when_flow_is_none() -> None:
    kwargs = _base_kwargs()
    kwargs["flow"] = None
    kwargs["flow_status"] = MarketEvaluationContourStatus.MISSING
    kwargs["outcome"] = MarketEvaluationOutcome.INSUFFICIENT_EVIDENCE
    kwargs["overall_quality"] = FeatureQuality.UNAVAILABLE
    # flow_quality still VALID -> inconsistent
    with pytest.raises(ValidationError):
        MarketEvaluationResult(**kwargs)


def test_flow_status_must_map_from_flow_outcome() -> None:
    kwargs = _base_kwargs()
    kwargs["flow_status"] = MarketEvaluationContourStatus.PARTIAL  # flow is actually ANALYZED
    with pytest.raises(ValidationError):
        MarketEvaluationResult(**kwargs)


def test_flow_quality_must_equal_flow_overall_quality() -> None:
    kwargs = _base_kwargs()
    kwargs["flow_quality"] = FeatureQuality.STALE  # flow.overall_quality is actually VALID
    with pytest.raises(ValidationError):
        MarketEvaluationResult(**kwargs)


# --- B. top-level outcome truth table ---


def test_outcome_must_match_truth_table() -> None:
    kwargs = _base_kwargs()
    kwargs["outcome"] = MarketEvaluationOutcome.EVALUATED  # only flow ANALYZED -> should be PARTIAL
    with pytest.raises(ValidationError):
        MarketEvaluationResult(**kwargs)


def test_evaluated_requires_all_three_analyzed() -> None:
    kwargs = _base_kwargs()
    kwargs["outcome"] = MarketEvaluationOutcome.INSUFFICIENT_EVIDENCE  # actually PARTIAL (flow analyzed)
    with pytest.raises(ValidationError):
        MarketEvaluationResult(**kwargs)


# --- C. overall_quality ---


def test_overall_quality_must_match_fold() -> None:
    kwargs = _base_kwargs()
    kwargs["overall_quality"] = FeatureQuality.STALE  # only qualifying contour (flow) is VALID
    with pytest.raises(ValidationError):
        MarketEvaluationResult(**kwargs)


def test_overall_quality_unavailable_when_zero_qualifying() -> None:
    kwargs = _base_kwargs()
    kwargs["flow"] = None
    kwargs["flow_status"] = MarketEvaluationContourStatus.MISSING
    kwargs["flow_quality"] = None
    kwargs["outcome"] = MarketEvaluationOutcome.INSUFFICIENT_EVIDENCE
    kwargs["overall_quality"] = FeatureQuality.VALID  # should be UNAVAILABLE
    with pytest.raises(ValidationError):
        MarketEvaluationResult(**kwargs)


# --- D. external alignment state ---


def test_alignment_status_missing_requires_external_none() -> None:
    kwargs = _base_kwargs()
    kwargs["external_alignment_status"] = ExternalAlignmentStatus.NO_MATCHING_SCOPE  # external is None
    with pytest.raises(ValidationError):
        MarketEvaluationResult(**kwargs)


def test_alignment_tuple_must_be_empty_when_external_none() -> None:
    kwargs = _base_kwargs()
    kwargs["external_scope_alignment"] = (
        ExternalScopeAlignmentRef(scope_summary_index=0, matched_by=ExternalScopeMatchKind.SYMBOL),
    )
    with pytest.raises(ValidationError):
        MarketEvaluationResult(**kwargs)


# --- E. alignment indexes ---


def test_alignment_index_out_of_range_rejected() -> None:
    from tests.market_evaluation_support import full_external_result

    external = full_external_result()
    kwargs = _base_kwargs()
    kwargs["external"] = external
    kwargs["external_status"] = MarketEvaluationContourStatus.ANALYZED
    kwargs["external_quality"] = external.overall_quality
    kwargs["outcome"] = MarketEvaluationOutcome.PARTIAL
    kwargs["overall_quality"] = FeatureQuality.VALID
    kwargs["external_alignment_status"] = ExternalAlignmentStatus.MATCHED
    kwargs["external_scope_alignment"] = (
        ExternalScopeAlignmentRef(scope_summary_index=999, matched_by=ExternalScopeMatchKind.SYMBOL),
    )
    with pytest.raises(ValidationError):
        MarketEvaluationResult(**kwargs)


def test_negative_alignment_index_rejected() -> None:
    with pytest.raises(ValidationError):
        ExternalScopeAlignmentRef(scope_summary_index=-1, matched_by=ExternalScopeMatchKind.SYMBOL)


# --- F. matched_by correctness ---


def test_matched_by_symbol_requires_news_sentiment_scope() -> None:
    from tests.market_evaluation_support import full_external_result

    external = full_external_result()
    # find a non-NEWS_SENTIMENT scope index
    non_news_index = next(
        i for i, s in enumerate(external.scope_summaries) if s.analyst_type.value != "NEWS_SENTIMENT"
    )
    kwargs = _base_kwargs()
    kwargs["external"] = external
    kwargs["external_status"] = MarketEvaluationContourStatus.ANALYZED
    kwargs["external_quality"] = external.overall_quality
    kwargs["outcome"] = MarketEvaluationOutcome.PARTIAL
    kwargs["overall_quality"] = FeatureQuality.VALID
    kwargs["external_alignment_status"] = ExternalAlignmentStatus.MATCHED
    kwargs["external_scope_alignment"] = (
        ExternalScopeAlignmentRef(scope_summary_index=non_news_index, matched_by=ExternalScopeMatchKind.SYMBOL),
    )
    with pytest.raises(ValidationError):
        MarketEvaluationResult(**kwargs)


def test_matched_by_currency_requires_context_currency_exposure() -> None:
    from tests.market_evaluation_support import full_external_result

    external = full_external_result()
    macro_index = next(i for i, s in enumerate(external.scope_summaries) if s.analyst_type.value == "MACRO_EVENT")
    kwargs = _base_kwargs()
    kwargs["context"] = make_context()  # no currency_exposures declared
    kwargs["external"] = external
    kwargs["external_status"] = MarketEvaluationContourStatus.ANALYZED
    kwargs["external_quality"] = external.overall_quality
    kwargs["outcome"] = MarketEvaluationOutcome.PARTIAL
    kwargs["overall_quality"] = FeatureQuality.VALID
    kwargs["external_alignment_status"] = ExternalAlignmentStatus.MATCHED
    kwargs["external_scope_alignment"] = (
        ExternalScopeAlignmentRef(scope_summary_index=macro_index, matched_by=ExternalScopeMatchKind.CURRENCY),
    )
    with pytest.raises(ValidationError):
        MarketEvaluationResult(**kwargs)


# --- Immutability / hygiene ---


def test_result_is_frozen() -> None:
    result = MarketEvaluationResult(**_base_kwargs())
    with pytest.raises(ValidationError):
        result.outcome = MarketEvaluationOutcome.EVALUATED  # type: ignore[misc]


def test_result_forbids_unknown_fields() -> None:
    kwargs = _base_kwargs()
    kwargs["unexpected_field"] = "value"
    with pytest.raises(ValidationError):
        MarketEvaluationResult(**kwargs)


def test_result_has_no_provenance_field() -> None:
    assert "provenance" not in MarketEvaluationResult.model_fields
