"""Stage 4G determinism and canonicalization tests.

Input order must never change the result: canonical ordering is
``analyst_type`` enum-declaration order, then native-scope order, computed
explicitly rather than relying on input/dict/set ordering.
"""

from __future__ import annotations

import random

from app.core.enums.external_intelligence_analysis import ExternalIntelligenceAnalystType
from app.external_intelligence_supervisor.supervisor import DEFAULT_EXPECTED_ANALYSTS, ExternalIntelligenceSupervisor
from tests.external_intelligence_supervisor_support import (
    NOW,
    OTHER_ASSET,
    OTHER_CURRENCY,
    OTHER_NETWORK,
    OTHER_SYMBOL,
    analyzed_result,
    full_analyzed_set,
)


def _multi_scope_set() -> tuple:
    return (
        analyzed_result(ExternalIntelligenceAnalystType.MACRO_EVENT),
        analyzed_result(ExternalIntelligenceAnalystType.MACRO_EVENT, currency=OTHER_CURRENCY),
        analyzed_result(ExternalIntelligenceAnalystType.NEWS_SENTIMENT),
        analyzed_result(ExternalIntelligenceAnalystType.NEWS_SENTIMENT, symbol=OTHER_SYMBOL),
        analyzed_result(ExternalIntelligenceAnalystType.ON_CHAIN),
        analyzed_result(ExternalIntelligenceAnalystType.ON_CHAIN, asset=OTHER_ASSET, network=OTHER_NETWORK),
    )


def test_input_order_does_not_change_result() -> None:
    results = list(_multi_scope_set())
    shuffled = results[::-1]

    supervisor = ExternalIntelligenceSupervisor()
    result_in_order = supervisor.aggregate(results, analysis_time=NOW)
    result_shuffled = supervisor.aggregate(shuffled, analysis_time=NOW)

    assert result_in_order == result_shuffled


def test_every_permutation_gives_identical_output() -> None:
    results = list(_multi_scope_set())
    supervisor = ExternalIntelligenceSupervisor()
    baseline = supervisor.aggregate(results, analysis_time=NOW)

    rng = random.Random(7)
    for _ in range(5):
        shuffled = results[:]
        rng.shuffle(shuffled)
        assert supervisor.aggregate(shuffled, analysis_time=NOW) == baseline


def test_analysis_results_use_canonical_analyst_type_order() -> None:
    results = list(full_analyzed_set())
    random.Random(42).shuffle(results)

    result = ExternalIntelligenceSupervisor().aggregate(results, analysis_time=NOW)

    provided_types = {r.analyst_type for r in results}
    expected_order = tuple(t for t in ExternalIntelligenceAnalystType if t in provided_types)
    assert tuple(r.analyst_type for r in result.analysis_results) == expected_order


def test_scope_summaries_share_canonical_order_with_analysis_results() -> None:
    results = list(_multi_scope_set())
    random.Random(3).shuffle(results)

    result = ExternalIntelligenceSupervisor().aggregate(results, analysis_time=NOW)
    assert tuple(s.analyst_type for s in result.scope_summaries) == tuple(
        r.analyst_type for r in result.analysis_results
    )
    for idx, summary in enumerate(result.scope_summaries):
        assert summary.result_index == idx


def test_participation_tuples_use_canonical_order() -> None:
    result = ExternalIntelligenceSupervisor().aggregate(full_analyzed_set(), analysis_time=NOW)
    expected_order = tuple(t for t in ExternalIntelligenceAnalystType if t in DEFAULT_EXPECTED_ANALYSTS)
    assert result.analyzed_analyst_types == expected_order
    assert result.expected_analyst_types == expected_order


def test_repeated_calls_are_identical() -> None:
    results = full_analyzed_set()
    supervisor = ExternalIntelligenceSupervisor()

    first = supervisor.aggregate(results, analysis_time=NOW)
    second = supervisor.aggregate(results, analysis_time=NOW)

    assert first == second


def test_same_instance_multiple_scopes_without_leakage() -> None:
    supervisor = ExternalIntelligenceSupervisor()

    macro_usd = (analyzed_result(ExternalIntelligenceAnalystType.MACRO_EVENT),)
    macro_eur = (analyzed_result(ExternalIntelligenceAnalystType.MACRO_EVENT, currency=OTHER_CURRENCY),)

    usd_result = supervisor.aggregate(macro_usd, analysis_time=NOW)
    eur_result = supervisor.aggregate(macro_eur, analysis_time=NOW)

    assert usd_result.scope_summaries[0].currency != eur_result.scope_summaries[0].currency

    usd_result_again = supervisor.aggregate(macro_usd, analysis_time=NOW)
    assert usd_result_again == usd_result
