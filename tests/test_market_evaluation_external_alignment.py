"""Stage 5A External Intelligence structural scope-alignment tests.

Exact identity matching only - no fuzzy matching, normalization, aliasing,
or symbol parsing. Unmatched scopes are legitimate, never an error, and
remain fully present in the embedded result while being omitted from
``external_scope_alignment``.
"""

from __future__ import annotations

from functools import partial

from app.core.enums.external_intelligence_analysis import ExternalIntelligenceAnalystType
from app.core.enums.market_evaluation import ExternalAlignmentStatus, ExternalScopeMatchKind, MarketEvaluationContourStatus
from app.core.models.market_evaluation_result import ExternalScopeAlignmentRef
from app.market_evaluation.evaluator import MarketEvaluator
from tests.external_intelligence_supervisor_support import analyzed_result as _base_ext_analyzed_result
from tests.market_evaluation_support import (
    ASSET,
    CURRENCY,
    NETWORK,
    NOW,
    OTHER_ASSET,
    OTHER_CURRENCY,
    OTHER_NETWORK,
    OTHER_SYMBOL,
    SYMBOL,
    external_result_with_scopes,
    make_context,
)

ext_analyzed_result = partial(_base_ext_analyzed_result, analysis_time=NOW)
"""Stage 4F's own support module defaults ``analysis_time`` to its own
``NOW`` constant, which differs from this suite's ``NOW`` - bind this
suite's ``NOW`` explicitly so every built result shares one consistent
analysis instant."""


def _evaluate(external, context):
    return MarketEvaluator().evaluate(flow=None, technical=None, external=external, context=context, evaluation_time=NOW)


# --- Individual match kinds (items 19-26) ---


def test_news_symbol_alignment() -> None:
    external = external_result_with_scopes((ext_analyzed_result(ExternalIntelligenceAnalystType.NEWS_SENTIMENT, symbol=SYMBOL),))
    result = _evaluate(external, make_context(symbol=SYMBOL))
    assert result.external_scope_alignment == (
        ExternalScopeAlignmentRef(scope_summary_index=0, matched_by=ExternalScopeMatchKind.SYMBOL),
    )
    assert result.external_alignment_status is ExternalAlignmentStatus.MATCHED


def test_news_symbol_mismatch_is_unmatched() -> None:
    external = external_result_with_scopes((ext_analyzed_result(ExternalIntelligenceAnalystType.NEWS_SENTIMENT, symbol=SYMBOL),))
    result = _evaluate(external, make_context(symbol=OTHER_SYMBOL))
    assert result.external_scope_alignment == ()
    assert result.external_alignment_status is ExternalAlignmentStatus.NO_MATCHING_SCOPE


def test_on_chain_asset_network_alignment() -> None:
    external = external_result_with_scopes(
        (ext_analyzed_result(ExternalIntelligenceAnalystType.ON_CHAIN, asset=ASSET, network=NETWORK),)
    )
    context = make_context(base_asset=ASSET, network=NETWORK)
    result = _evaluate(external, context)
    assert len(result.external_scope_alignment) == 1
    assert result.external_scope_alignment[0].matched_by is ExternalScopeMatchKind.ASSET_NETWORK
    assert result.external_alignment_status is ExternalAlignmentStatus.MATCHED


def test_on_chain_mismatch_is_unmatched() -> None:
    external = external_result_with_scopes(
        (ext_analyzed_result(ExternalIntelligenceAnalystType.ON_CHAIN, asset=ASSET, network=NETWORK),)
    )
    context = make_context(base_asset=OTHER_ASSET, network=OTHER_NETWORK)
    result = _evaluate(external, context)
    assert result.external_scope_alignment == ()
    assert result.external_alignment_status is ExternalAlignmentStatus.NO_MATCHING_SCOPE


def test_on_chain_mapping_absent_from_context_is_unmatched() -> None:
    external = external_result_with_scopes(
        (ext_analyzed_result(ExternalIntelligenceAnalystType.ON_CHAIN, asset=ASSET, network=NETWORK),)
    )
    context = make_context()  # no base_asset/network declared
    result = _evaluate(external, context)
    assert result.external_scope_alignment == ()
    assert result.external_alignment_status is ExternalAlignmentStatus.NO_MATCHING_SCOPE


def test_macro_currency_alignment() -> None:
    external = external_result_with_scopes(
        (ext_analyzed_result(ExternalIntelligenceAnalystType.MACRO_EVENT, currency=CURRENCY),)
    )
    context = make_context(currency_exposures=(CURRENCY,))
    result = _evaluate(external, context)
    assert len(result.external_scope_alignment) == 1
    assert result.external_scope_alignment[0].matched_by is ExternalScopeMatchKind.CURRENCY
    assert result.external_alignment_status is ExternalAlignmentStatus.MATCHED


def test_rates_currency_alignment() -> None:
    external = external_result_with_scopes(
        (ext_analyzed_result(ExternalIntelligenceAnalystType.RATES_YIELD, currency=CURRENCY),)
    )
    context = make_context(currency_exposures=(CURRENCY,))
    result = _evaluate(external, context)
    assert len(result.external_scope_alignment) == 1
    assert result.external_scope_alignment[0].matched_by is ExternalScopeMatchKind.CURRENCY
    assert result.external_alignment_status is ExternalAlignmentStatus.MATCHED


def test_currency_not_declared_is_unmatched() -> None:
    external = external_result_with_scopes(
        (ext_analyzed_result(ExternalIntelligenceAnalystType.MACRO_EVENT, currency=CURRENCY),)
    )
    context = make_context(currency_exposures=(OTHER_CURRENCY,))
    result = _evaluate(external, context)
    assert result.external_scope_alignment == ()
    assert result.external_alignment_status is ExternalAlignmentStatus.NO_MATCHING_SCOPE


# --- Multiple scopes (items 27-31) ---


def test_multiple_matched_external_scopes() -> None:
    external = external_result_with_scopes(
        (
            ext_analyzed_result(ExternalIntelligenceAnalystType.NEWS_SENTIMENT, symbol=SYMBOL),
            ext_analyzed_result(ExternalIntelligenceAnalystType.MACRO_EVENT, currency=CURRENCY),
            ext_analyzed_result(ExternalIntelligenceAnalystType.RATES_YIELD, currency=CURRENCY),
            ext_analyzed_result(ExternalIntelligenceAnalystType.ON_CHAIN, asset=ASSET, network=NETWORK),
        )
    )
    context = make_context(symbol=SYMBOL, base_asset=ASSET, network=NETWORK, currency_exposures=(CURRENCY,))
    result = _evaluate(external, context)
    assert len(result.external_scope_alignment) == 4
    assert result.external_alignment_status is ExternalAlignmentStatus.MATCHED


def test_multiple_unmatched_scopes() -> None:
    external = external_result_with_scopes(
        (
            ext_analyzed_result(ExternalIntelligenceAnalystType.NEWS_SENTIMENT, symbol=OTHER_SYMBOL),
            ext_analyzed_result(ExternalIntelligenceAnalystType.MACRO_EVENT, currency=OTHER_CURRENCY),
        )
    )
    context = make_context(symbol=SYMBOL, currency_exposures=(CURRENCY,))
    result = _evaluate(external, context)
    assert result.external_scope_alignment == ()
    assert result.external_alignment_status is ExternalAlignmentStatus.NO_MATCHING_SCOPE


def test_matched_and_unmatched_scopes_together() -> None:
    external = external_result_with_scopes(
        (
            ext_analyzed_result(ExternalIntelligenceAnalystType.NEWS_SENTIMENT, symbol=SYMBOL),
            ext_analyzed_result(ExternalIntelligenceAnalystType.NEWS_SENTIMENT, symbol=OTHER_SYMBOL),
        )
    )
    context = make_context(symbol=SYMBOL)
    result = _evaluate(external, context)
    assert len(result.external_scope_alignment) == 1
    assert result.external_scope_alignment[0].scope_summary_index == 0
    assert result.external_alignment_status is ExternalAlignmentStatus.MATCHED


def test_unmatched_scopes_retained_in_embedded_result() -> None:
    external = external_result_with_scopes(
        (
            ext_analyzed_result(ExternalIntelligenceAnalystType.NEWS_SENTIMENT, symbol=SYMBOL),
            ext_analyzed_result(ExternalIntelligenceAnalystType.NEWS_SENTIMENT, symbol=OTHER_SYMBOL),
        )
    )
    context = make_context(symbol=SYMBOL)
    result = _evaluate(external, context)
    assert len(result.external.scope_summaries) == 2
    assert {s.symbol for s in result.external.scope_summaries} == {SYMBOL, OTHER_SYMBOL}


def test_unmatched_scopes_omitted_from_alignment_tuple() -> None:
    external = external_result_with_scopes(
        (
            ext_analyzed_result(ExternalIntelligenceAnalystType.NEWS_SENTIMENT, symbol=SYMBOL),
            ext_analyzed_result(ExternalIntelligenceAnalystType.NEWS_SENTIMENT, symbol=OTHER_SYMBOL),
        )
    )
    context = make_context(symbol=SYMBOL)
    result = _evaluate(external, context)
    matched_indexes = {ref.scope_summary_index for ref in result.external_scope_alignment}
    assert matched_indexes == {0}


# --- ANALYZED + NO_MATCHING_SCOPE coexistence (item 32) ---


def test_external_analyzed_with_no_matching_scope_is_valid() -> None:
    external = external_result_with_scopes(
        (ext_analyzed_result(ExternalIntelligenceAnalystType.NEWS_SENTIMENT, symbol=OTHER_SYMBOL),)
    )
    context = make_context(symbol=SYMBOL)
    result = _evaluate(external, context)
    assert result.external_status is MarketEvaluationContourStatus.PARTIAL  # only NEWS_SENTIMENT of 4 types analyzed
    assert result.external_alignment_status is ExternalAlignmentStatus.NO_MATCHING_SCOPE
    assert result.external_quality is not None


# --- ExternalAlignmentStatus truth table (items 33-35) ---


def test_alignment_status_missing_when_external_none() -> None:
    result = MarketEvaluator().evaluate(
        flow=None, technical=None, external=None, context=make_context(), evaluation_time=NOW
    )
    assert result.external_alignment_status is ExternalAlignmentStatus.MISSING
    assert result.external_scope_alignment == ()


def test_alignment_status_no_matching_scope() -> None:
    external = external_result_with_scopes(
        (ext_analyzed_result(ExternalIntelligenceAnalystType.NEWS_SENTIMENT, symbol=OTHER_SYMBOL),)
    )
    result = _evaluate(external, make_context(symbol=SYMBOL))
    assert result.external_alignment_status is ExternalAlignmentStatus.NO_MATCHING_SCOPE


def test_alignment_status_matched() -> None:
    external = external_result_with_scopes((ext_analyzed_result(ExternalIntelligenceAnalystType.NEWS_SENTIMENT, symbol=SYMBOL),))
    result = _evaluate(external, make_context(symbol=SYMBOL))
    assert result.external_alignment_status is ExternalAlignmentStatus.MATCHED


# --- Index validity and matched_by consistency (items 36-37) ---


def test_alignment_index_resolves_into_scope_summaries() -> None:
    external = external_result_with_scopes((ext_analyzed_result(ExternalIntelligenceAnalystType.NEWS_SENTIMENT, symbol=SYMBOL),))
    result = _evaluate(external, make_context(symbol=SYMBOL))
    for ref in result.external_scope_alignment:
        assert 0 <= ref.scope_summary_index < len(result.external.scope_summaries)


def test_matched_by_matches_native_analyst_family() -> None:
    external = external_result_with_scopes(
        (
            ext_analyzed_result(ExternalIntelligenceAnalystType.NEWS_SENTIMENT, symbol=SYMBOL),
            ext_analyzed_result(ExternalIntelligenceAnalystType.MACRO_EVENT, currency=CURRENCY),
            ext_analyzed_result(ExternalIntelligenceAnalystType.ON_CHAIN, asset=ASSET, network=NETWORK),
        )
    )
    context = make_context(symbol=SYMBOL, base_asset=ASSET, network=NETWORK, currency_exposures=(CURRENCY,))
    result = _evaluate(external, context)

    by_kind = {ref.matched_by: result.external.scope_summaries[ref.scope_summary_index].analyst_type for ref in result.external_scope_alignment}
    assert by_kind[ExternalScopeMatchKind.SYMBOL] is ExternalIntelligenceAnalystType.NEWS_SENTIMENT
    assert by_kind[ExternalScopeMatchKind.CURRENCY] is ExternalIntelligenceAnalystType.MACRO_EVENT
    assert by_kind[ExternalScopeMatchKind.ASSET_NETWORK] is ExternalIntelligenceAnalystType.ON_CHAIN
