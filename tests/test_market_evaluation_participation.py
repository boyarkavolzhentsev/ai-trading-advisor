"""Stage 5A contour-status mapping and top-level outcome truth-table tests.

Scope-alignment relevance must never influence the top-level
``MarketEvaluationOutcome``.
"""

from __future__ import annotations

from app.core.enums.market_evaluation import MarketEvaluationContourStatus, MarketEvaluationOutcome
from app.core.enums.quality import FeatureQuality
from app.market_evaluation.evaluator import MarketEvaluator
from tests.market_evaluation_support import (
    NOW,
    OTHER_SYMBOL,
    full_external_result,
    full_flow_result,
    full_technical_result,
    insufficient_external_result,
    insufficient_flow_result,
    insufficient_technical_result,
    make_context,
    partial_external_result,
    partial_flow_result,
    partial_technical_result,
)


def _evaluate(*, flow=None, technical=None, external=None, context=None):
    return MarketEvaluator().evaluate(
        flow=flow, technical=technical, external=external, context=context or make_context(), evaluation_time=NOW
    )


# --- Contour status mapping (item 2) ---


def test_missing_contour_maps_to_missing_status() -> None:
    result = _evaluate()
    assert result.flow_status is MarketEvaluationContourStatus.MISSING
    assert result.technical_status is MarketEvaluationContourStatus.MISSING
    assert result.external_status is MarketEvaluationContourStatus.MISSING


def test_native_analyzed_maps_to_analyzed_status() -> None:
    result = _evaluate(flow=full_flow_result())
    assert result.flow_status is MarketEvaluationContourStatus.ANALYZED


def test_native_partial_maps_to_partial_status() -> None:
    result = _evaluate(flow=partial_flow_result())
    assert result.flow_status is MarketEvaluationContourStatus.PARTIAL


def test_native_insufficient_evidence_maps_to_insufficient_evidence_status() -> None:
    result = _evaluate(flow=insufficient_flow_result())
    assert result.flow_status is MarketEvaluationContourStatus.INSUFFICIENT_EVIDENCE


# --- Empty input (item 4) ---


def test_empty_input_is_insufficient_evidence() -> None:
    result = _evaluate()
    assert result.outcome is MarketEvaluationOutcome.INSUFFICIENT_EVIDENCE
    assert result.overall_quality is FeatureQuality.UNAVAILABLE


# --- Single contour (items 5-7) ---


def test_flow_only_analyzed_is_partial() -> None:
    result = _evaluate(flow=full_flow_result())
    assert result.outcome is MarketEvaluationOutcome.PARTIAL


def test_technical_only_analyzed_is_partial() -> None:
    result = _evaluate(technical=full_technical_result())
    assert result.outcome is MarketEvaluationOutcome.PARTIAL


def test_external_only_analyzed_is_partial() -> None:
    result = _evaluate(external=full_external_result())
    assert result.outcome is MarketEvaluationOutcome.PARTIAL


# --- Two-contour combinations (item 8) ---


def test_flow_and_technical_analyzed_is_partial() -> None:
    result = _evaluate(flow=full_flow_result(), technical=full_technical_result())
    assert result.outcome is MarketEvaluationOutcome.PARTIAL


def test_flow_and_external_analyzed_is_partial() -> None:
    result = _evaluate(flow=full_flow_result(), external=full_external_result())
    assert result.outcome is MarketEvaluationOutcome.PARTIAL


def test_technical_and_external_analyzed_is_partial() -> None:
    result = _evaluate(technical=full_technical_result(), external=full_external_result())
    assert result.outcome is MarketEvaluationOutcome.PARTIAL


# --- All three contours (item 9) ---


def test_all_three_analyzed_is_evaluated() -> None:
    result = _evaluate(flow=full_flow_result(), technical=full_technical_result(), external=full_external_result())
    assert result.outcome is MarketEvaluationOutcome.EVALUATED


# --- Full truth table per the finalized design ---


def test_missing_missing_missing_is_insufficient_evidence() -> None:
    assert _evaluate().outcome is MarketEvaluationOutcome.INSUFFICIENT_EVIDENCE


def test_insufficient_missing_missing_is_insufficient_evidence() -> None:
    result = _evaluate(flow=insufficient_flow_result())
    assert result.outcome is MarketEvaluationOutcome.INSUFFICIENT_EVIDENCE


def test_insufficient_insufficient_insufficient_is_insufficient_evidence() -> None:
    result = _evaluate(
        flow=insufficient_flow_result(), technical=insufficient_technical_result(), external=insufficient_external_result()
    )
    assert result.outcome is MarketEvaluationOutcome.INSUFFICIENT_EVIDENCE


def test_partial_missing_missing_is_partial() -> None:
    result = _evaluate(flow=partial_flow_result())
    assert result.outcome is MarketEvaluationOutcome.PARTIAL


def test_analyzed_missing_missing_is_partial() -> None:
    result = _evaluate(flow=full_flow_result())
    assert result.outcome is MarketEvaluationOutcome.PARTIAL


def test_analyzed_analyzed_missing_is_partial() -> None:
    result = _evaluate(flow=full_flow_result(), technical=full_technical_result())
    assert result.outcome is MarketEvaluationOutcome.PARTIAL


def test_analyzed_analyzed_analyzed_is_evaluated() -> None:
    result = _evaluate(flow=full_flow_result(), technical=full_technical_result(), external=full_external_result())
    assert result.outcome is MarketEvaluationOutcome.EVALUATED


def test_mixed_partial_and_insufficient_is_partial() -> None:
    result = _evaluate(flow=partial_flow_result(), technical=insufficient_technical_result())
    assert result.outcome is MarketEvaluationOutcome.PARTIAL


# --- Scope alignment must never influence outcome (item 45) ---


def test_no_matching_external_scope_does_not_change_outcome() -> None:
    # context.symbol differs from every default external scope's own symbol/currency/asset,
    # and declares no currency_exposures/base_asset/network - so nothing can match.
    context = make_context(symbol=OTHER_SYMBOL)
    result = _evaluate(
        flow=full_flow_result(symbol=OTHER_SYMBOL),
        technical=full_technical_result(symbol=OTHER_SYMBOL),
        external=full_external_result(),
        context=context,
    )
    assert result.external_status is MarketEvaluationContourStatus.ANALYZED
    from app.core.enums.market_evaluation import ExternalAlignmentStatus

    assert result.external_alignment_status is ExternalAlignmentStatus.NO_MATCHING_SCOPE
    # Every contour is still fully ANALYZED at the participation level - alignment relevance
    # never demotes participation, so the outcome remains EVALUATED.
    assert result.outcome is MarketEvaluationOutcome.EVALUATED
