"""Stage 6A structural eligibility rules, per ``StrategyFamily``.

Covers every allowed/disallowed ``MarketEvaluationContourStatus``, every
allowed/disallowed ``FeatureQuality``, ``BREAKOUT``'s two independent
required contours, ``EVENT_DRIVEN``'s external-alignment rule (including the
approved MISSING-contour clarification), and cases where multiple
independent structural facts fail simultaneously (no short-circuiting).
"""

from __future__ import annotations

import pytest

from app.core.enums.external_intelligence_analysis import ExternalIntelligenceAnalystType
from app.core.enums.quality import FeatureQuality
from app.core.enums.strategy_router import StrategyFamily, StrategyIneligibilityReason
from app.external_intelligence_supervisor.supervisor import ExternalIntelligenceSupervisor
from app.strategies.router import StrategyRouter
from tests.external_intelligence_supervisor_support import analyzed_result as ext_analyzed_result
from tests.market_evaluation_support import (
    OTHER_SYMBOL,
    full_external_result,
    full_flow_result,
    full_technical_result,
    insufficient_external_result,
    insufficient_flow_result,
    insufficient_technical_result,
    make_context,
)
from tests.strategy_router_support import (
    NOW,
    SYMBOL,
    evaluation,
    external_result_matched,
    external_result_unmatched,
    external_result_with_quality,
    flow_result_with_quality,
    technical_result_with_quality,
)

CONTOUR_ONLY_FAMILIES = (StrategyFamily.TREND_FOLLOWING, StrategyFamily.MEAN_REVERSION)


def _entry(result, family):
    matches = [entry for entry in result.eligibility if entry.family is family]
    assert len(matches) == 1
    return matches[0]


# --- TREND_FOLLOWING / MEAN_REVERSION: technical-only rule ---


@pytest.mark.parametrize("family", CONTOUR_ONLY_FAMILIES, ids=lambda f: f.value)
def test_technical_missing_is_ineligible(family) -> None:
    result = StrategyRouter().route(market_evaluation=evaluation(technical=None))
    entry = _entry(result, family)
    assert entry.eligible is False
    assert entry.ineligibility_reasons == (StrategyIneligibilityReason.CONTOUR_MISSING,)


@pytest.mark.parametrize("family", CONTOUR_ONLY_FAMILIES, ids=lambda f: f.value)
def test_technical_insufficient_evidence_yields_two_independent_reasons(family) -> None:
    """``insufficient_technical_result()`` is structurally both
    ``INSUFFICIENT_EVIDENCE`` status and ``UNAVAILABLE`` quality - both
    independent facts must be reported, never short-circuited."""
    me = evaluation(technical=insufficient_technical_result())
    result = StrategyRouter().route(market_evaluation=me)
    entry = _entry(result, family)
    assert entry.eligible is False
    assert entry.ineligibility_reasons == (
        StrategyIneligibilityReason.CONTOUR_INSUFFICIENT_EVIDENCE,
        StrategyIneligibilityReason.QUALITY_UNAVAILABLE,
    )


@pytest.mark.parametrize("family", CONTOUR_ONLY_FAMILIES, ids=lambda f: f.value)
@pytest.mark.parametrize("quality", [FeatureQuality.VALID, FeatureQuality.PARTIAL, FeatureQuality.STALE])
def test_technical_partial_status_with_allowed_quality_is_eligible(family, quality) -> None:
    me = evaluation(technical=technical_result_with_quality(quality))
    result = StrategyRouter().route(market_evaluation=me)
    entry = _entry(result, family)
    assert entry.eligible is True
    assert entry.ineligibility_reasons == ()


@pytest.mark.parametrize("family", CONTOUR_ONLY_FAMILIES, ids=lambda f: f.value)
def test_technical_partial_status_with_unavailable_quality_is_ineligible(family) -> None:
    me = evaluation(technical=technical_result_with_quality(FeatureQuality.UNAVAILABLE))
    result = StrategyRouter().route(market_evaluation=me)
    entry = _entry(result, family)
    assert entry.eligible is False
    assert entry.ineligibility_reasons == (StrategyIneligibilityReason.QUALITY_UNAVAILABLE,)


@pytest.mark.parametrize("family", CONTOUR_ONLY_FAMILIES, ids=lambda f: f.value)
def test_technical_analyzed_status_with_valid_quality_is_eligible(family) -> None:
    me = evaluation(technical=full_technical_result())
    result = StrategyRouter().route(market_evaluation=me)
    entry = _entry(result, family)
    assert entry.eligible is True
    assert entry.ineligibility_reasons == ()


# --- BREAKOUT: technical AND flow, both required independently ---


def test_breakout_eligible_when_both_technical_and_flow_usable() -> None:
    me = evaluation(technical=full_technical_result(), flow=full_flow_result())
    result = StrategyRouter().route(market_evaluation=me)
    entry = _entry(result, StrategyFamily.BREAKOUT)
    assert entry.eligible is True
    assert entry.ineligibility_reasons == ()


def test_breakout_ineligible_on_technical_failure_only() -> None:
    me = evaluation(technical=None, flow=full_flow_result())
    result = StrategyRouter().route(market_evaluation=me)
    entry = _entry(result, StrategyFamily.BREAKOUT)
    assert entry.eligible is False
    assert entry.ineligibility_reasons == (StrategyIneligibilityReason.CONTOUR_MISSING,)


def test_breakout_ineligible_on_flow_failure_only() -> None:
    me = evaluation(technical=full_technical_result(), flow=None)
    result = StrategyRouter().route(market_evaluation=me)
    entry = _entry(result, StrategyFamily.BREAKOUT)
    assert entry.eligible is False
    assert entry.ineligibility_reasons == (StrategyIneligibilityReason.CONTOUR_MISSING,)


def test_breakout_ineligible_on_both_failures_deduplicates_identical_reason() -> None:
    me = evaluation(technical=None, flow=None)
    result = StrategyRouter().route(market_evaluation=me)
    entry = _entry(result, StrategyFamily.BREAKOUT)
    assert entry.eligible is False
    assert entry.ineligibility_reasons == (StrategyIneligibilityReason.CONTOUR_MISSING,)


def test_breakout_combines_distinct_reasons_across_both_contours() -> None:
    """technical MISSING + flow INSUFFICIENT_EVIDENCE (itself UNAVAILABLE
    quality) must surface all three distinct, canonically-ordered reasons."""
    me = evaluation(technical=None, flow=insufficient_flow_result())
    result = StrategyRouter().route(market_evaluation=me)
    entry = _entry(result, StrategyFamily.BREAKOUT)
    assert entry.eligible is False
    assert entry.ineligibility_reasons == (
        StrategyIneligibilityReason.CONTOUR_MISSING,
        StrategyIneligibilityReason.CONTOUR_INSUFFICIENT_EVIDENCE,
        StrategyIneligibilityReason.QUALITY_UNAVAILABLE,
    )


def test_breakout_ineligible_on_one_contour_quality_unavailable() -> None:
    me = evaluation(
        technical=technical_result_with_quality(FeatureQuality.VALID),
        flow=flow_result_with_quality(FeatureQuality.UNAVAILABLE),
    )
    result = StrategyRouter().route(market_evaluation=me)
    entry = _entry(result, StrategyFamily.BREAKOUT)
    assert entry.eligible is False
    assert entry.ineligibility_reasons == (StrategyIneligibilityReason.QUALITY_UNAVAILABLE,)


# --- EVENT_DRIVEN: external contour + alignment ---


def test_event_driven_external_missing_is_ineligible_without_alignment_reason() -> None:
    """Approved clarification: external MISSING must report only
    CONTOUR_MISSING, never additionally EXTERNAL_SCOPE_NOT_ALIGNED."""
    me = evaluation(external=None)
    result = StrategyRouter().route(market_evaluation=me)
    entry = _entry(result, StrategyFamily.EVENT_DRIVEN)
    assert entry.eligible is False
    assert entry.ineligibility_reasons == (StrategyIneligibilityReason.CONTOUR_MISSING,)


def test_event_driven_external_insufficient_evidence_still_evaluates_alignment() -> None:
    """External structurally present with INSUFFICIENT_EVIDENCE status: the
    alignment check still applies (three independent facts fail here)."""
    me = evaluation(external=insufficient_external_result())
    result = StrategyRouter().route(market_evaluation=me)
    entry = _entry(result, StrategyFamily.EVENT_DRIVEN)
    assert entry.eligible is False
    assert entry.ineligibility_reasons == (
        StrategyIneligibilityReason.CONTOUR_INSUFFICIENT_EVIDENCE,
        StrategyIneligibilityReason.QUALITY_UNAVAILABLE,
        StrategyIneligibilityReason.EXTERNAL_SCOPE_NOT_ALIGNED,
    )


def test_event_driven_usable_but_unmatched_scope_is_ineligible() -> None:
    me = evaluation(external=external_result_with_quality(FeatureQuality.VALID))
    result = StrategyRouter().route(market_evaluation=me)
    entry = _entry(result, StrategyFamily.EVENT_DRIVEN)
    assert entry.eligible is False
    assert entry.ineligibility_reasons == (StrategyIneligibilityReason.EXTERNAL_SCOPE_NOT_ALIGNED,)


def test_event_driven_explicit_no_matching_scope_is_ineligible() -> None:
    me = evaluation(external=external_result_unmatched(), context=make_context())
    result = StrategyRouter().route(market_evaluation=me)
    entry = _entry(result, StrategyFamily.EVENT_DRIVEN)
    assert entry.eligible is False
    assert entry.ineligibility_reasons == (StrategyIneligibilityReason.EXTERNAL_SCOPE_NOT_ALIGNED,)


def test_event_driven_matched_scope_is_eligible() -> None:
    me = evaluation(external=external_result_matched(), context=make_context())
    result = StrategyRouter().route(market_evaluation=me)
    entry = _entry(result, StrategyFamily.EVENT_DRIVEN)
    assert entry.eligible is True
    assert entry.ineligibility_reasons == ()


def test_event_driven_quality_unavailable_and_unmatched_combine() -> None:
    me = evaluation(external=external_result_with_quality(FeatureQuality.UNAVAILABLE))
    result = StrategyRouter().route(market_evaluation=me)
    entry = _entry(result, StrategyFamily.EVENT_DRIVEN)
    assert entry.eligible is False
    assert entry.ineligibility_reasons == (
        StrategyIneligibilityReason.QUALITY_UNAVAILABLE,
        StrategyIneligibilityReason.EXTERNAL_SCOPE_NOT_ALIGNED,
    )


@pytest.mark.parametrize("quality", [FeatureQuality.VALID, FeatureQuality.PARTIAL, FeatureQuality.STALE])
def test_event_driven_allowed_quality_with_matched_scope_is_eligible(quality) -> None:
    # external_result_matched() always builds a VALID-quality analyst
    # result; re-derive with the parametrized quality via the same scope.
    external = ExternalIntelligenceSupervisor().aggregate(
        (
            ext_analyzed_result(
                ExternalIntelligenceAnalystType.NEWS_SENTIMENT, analysis_time=NOW, symbol=SYMBOL, quality=quality
            ),
        ),
        analysis_time=NOW,
    )
    me = evaluation(external=external, context=make_context())
    result = StrategyRouter().route(market_evaluation=me)
    entry = _entry(result, StrategyFamily.EVENT_DRIVEN)
    assert entry.eligible is True
    assert entry.ineligibility_reasons == ()


def test_event_driven_analyzed_status_full_result_but_unmatched_is_ineligible() -> None:
    """``full_external_result()`` yields ANALYZED status across every
    analyst type. Its NEWS_SENTIMENT scope defaults to the same symbol as
    ``make_context()``'s default, so it *would* align - build a context with
    a different symbol (and default/empty asset+network+currency_exposures,
    which already mismatch the ON_CHAIN/MACRO_EVENT/RATES_YIELD scopes) so
    nothing structurally aligns, to isolate alignment-only ineligibility."""
    me = evaluation(external=full_external_result(), context=make_context(symbol=OTHER_SYMBOL))
    result = StrategyRouter().route(market_evaluation=me)
    entry = _entry(result, StrategyFamily.EVENT_DRIVEN)
    assert entry.eligible is False
    assert entry.ineligibility_reasons == (StrategyIneligibilityReason.EXTERNAL_SCOPE_NOT_ALIGNED,)
