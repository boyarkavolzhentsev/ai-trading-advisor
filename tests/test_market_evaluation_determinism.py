"""Stage 5A determinism tests.

Repeated calls and structurally equivalent scope orderings must produce
identical results; ``external_scope_alignment`` ordering follows
``external.scope_summaries``'s own already-canonical order.
"""

from __future__ import annotations

from functools import partial

from app.core.enums.external_intelligence_analysis import ExternalIntelligenceAnalystType
from app.market_evaluation.evaluator import MarketEvaluator
from tests.external_intelligence_supervisor_support import analyzed_result as _base_ext_analyzed_result
from tests.market_evaluation_support import (
    ASSET,
    CURRENCY,
    NETWORK,
    NOW,
    OTHER_ASSET,
    OTHER_NETWORK,
    SYMBOL,
    external_result_with_scopes,
    full_external_result,
    full_flow_result,
    full_technical_result,
    make_context,
)

ext_analyzed_result = partial(_base_ext_analyzed_result, analysis_time=NOW)


def test_repeated_calls_are_identical() -> None:
    flow = full_flow_result()
    technical = full_technical_result()
    external = full_external_result()
    context = make_context()
    evaluator = MarketEvaluator()

    first = evaluator.evaluate(flow=flow, technical=technical, external=external, context=context, evaluation_time=NOW)
    second = evaluator.evaluate(flow=flow, technical=technical, external=external, context=context, evaluation_time=NOW)

    assert first == second


def test_alignment_ordering_follows_scope_summaries_canonical_order() -> None:
    external = external_result_with_scopes(
        (
            ext_analyzed_result(ExternalIntelligenceAnalystType.MACRO_EVENT, currency=CURRENCY),
            ext_analyzed_result(ExternalIntelligenceAnalystType.NEWS_SENTIMENT, symbol=SYMBOL),
            ext_analyzed_result(ExternalIntelligenceAnalystType.ON_CHAIN, asset=ASSET, network=NETWORK),
            ext_analyzed_result(ExternalIntelligenceAnalystType.ON_CHAIN, asset=OTHER_ASSET, network=OTHER_NETWORK),
        )
    )
    context = make_context(symbol=SYMBOL, base_asset=ASSET, network=NETWORK, currency_exposures=(CURRENCY,))
    result = MarketEvaluator().evaluate(flow=None, technical=None, external=external, context=context, evaluation_time=NOW)

    indexes = [ref.scope_summary_index for ref in result.external_scope_alignment]
    assert indexes == sorted(indexes)
    # canonical scope_summaries order must exactly mirror external.analysis_results order
    assert [s.analyst_type for s in external.scope_summaries] == sorted(
        [s.analyst_type for s in external.scope_summaries], key=lambda t: list(ExternalIntelligenceAnalystType).index(t)
    )


def test_same_evaluator_instance_multiple_contexts_without_leakage() -> None:
    evaluator = MarketEvaluator()
    flow_a = full_flow_result(symbol=SYMBOL)
    result_a = evaluator.evaluate(flow=flow_a, technical=None, external=None, context=make_context(symbol=SYMBOL), evaluation_time=NOW)

    from tests.market_evaluation_support import OTHER_SYMBOL

    flow_b = full_flow_result(symbol=OTHER_SYMBOL)
    result_b = evaluator.evaluate(
        flow=flow_b, technical=None, external=None, context=make_context(symbol=OTHER_SYMBOL), evaluation_time=NOW
    )

    assert result_a.context.symbol == SYMBOL
    assert result_b.context.symbol == OTHER_SYMBOL

    result_a_again = evaluator.evaluate(
        flow=flow_a, technical=None, external=None, context=make_context(symbol=SYMBOL), evaluation_time=NOW
    )
    assert result_a_again == result_a
