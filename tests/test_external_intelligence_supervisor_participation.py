"""Stage 4G participation / outcome tests.

Outcome is derived purely from analyst-*type* participation counts - never
from scope counts, never a vote, never a weighted ratio.
"""

from __future__ import annotations

from app.core.enums.external_intelligence_analysis import ExternalIntelligenceAnalystType
from app.core.enums.external_intelligence_supervisor import ExternalIntelligenceSupervisorOutcome
from app.core.enums.quality import FeatureQuality
from app.external_intelligence_supervisor.supervisor import ExternalIntelligenceSupervisor
from tests.external_intelligence_supervisor_support import (
    ASSET,
    NETWORK,
    NOW,
    OTHER_ASSET,
    OTHER_NETWORK,
    OTHER_SYMBOL,
    SYMBOL,
    abstained_result,
    analyzed_result,
    full_analyzed_set,
)


def test_empty_input_is_insufficient_evidence() -> None:
    result = ExternalIntelligenceSupervisor().aggregate((), analysis_time=NOW)
    assert result.outcome is ExternalIntelligenceSupervisorOutcome.INSUFFICIENT_EVIDENCE


def test_all_four_expected_types_analyzed_yields_analyzed() -> None:
    result = ExternalIntelligenceSupervisor().aggregate(full_analyzed_set(), analysis_time=NOW)
    assert result.outcome is ExternalIntelligenceSupervisorOutcome.ANALYZED
    assert set(result.analyzed_analyst_types) == set(ExternalIntelligenceAnalystType)
    assert result.abstained_analyst_types == ()
    assert result.missing_analyst_types == ()


def test_some_analyzed_some_missing_yields_partial() -> None:
    results = (analyzed_result(ExternalIntelligenceAnalystType.MACRO_EVENT),)
    result = ExternalIntelligenceSupervisor().aggregate(results, analysis_time=NOW)
    assert result.outcome is ExternalIntelligenceSupervisorOutcome.PARTIAL
    assert result.analyzed_analyst_types == (ExternalIntelligenceAnalystType.MACRO_EVENT,)
    assert ExternalIntelligenceAnalystType.RATES_YIELD in result.missing_analyst_types


def test_some_analyzed_some_abstained_yields_partial() -> None:
    results = (
        analyzed_result(ExternalIntelligenceAnalystType.MACRO_EVENT),
        abstained_result(ExternalIntelligenceAnalystType.RATES_YIELD),
    )
    result = ExternalIntelligenceSupervisor().aggregate(results, analysis_time=NOW)
    assert result.outcome is ExternalIntelligenceSupervisorOutcome.PARTIAL
    assert result.analyzed_analyst_types == (ExternalIntelligenceAnalystType.MACRO_EVENT,)
    assert result.abstained_analyst_types == (ExternalIntelligenceAnalystType.RATES_YIELD,)


def test_zero_analyzed_with_abstained_supplied_yields_insufficient_evidence() -> None:
    results = tuple(abstained_result(t) for t in ExternalIntelligenceAnalystType)
    result = ExternalIntelligenceSupervisor().aggregate(results, analysis_time=NOW)
    assert result.outcome is ExternalIntelligenceSupervisorOutcome.INSUFFICIENT_EVIDENCE
    assert result.analyzed_analyst_types == ()
    assert set(result.abstained_analyst_types) == set(ExternalIntelligenceAnalystType)


def test_zero_analyzed_all_missing_yields_insufficient_evidence() -> None:
    result = ExternalIntelligenceSupervisor().aggregate((), analysis_time=NOW)
    assert result.outcome is ExternalIntelligenceSupervisorOutcome.INSUFFICIENT_EVIDENCE
    assert set(result.missing_analyst_types) == set(ExternalIntelligenceAnalystType)


def test_many_scopes_for_one_type_still_count_as_one_analyst_type() -> None:
    on_chain_scopes = [(ASSET, NETWORK), (OTHER_ASSET, NETWORK), (ASSET, OTHER_NETWORK), (OTHER_ASSET, OTHER_NETWORK)]
    on_chain_results = tuple(
        analyzed_result(ExternalIntelligenceAnalystType.ON_CHAIN, asset=asset, network=network)
        for asset, network in on_chain_scopes
    )
    # Pad to 10 On-Chain scopes with distinct asset/network pairs.
    extra = tuple(
        analyzed_result(ExternalIntelligenceAnalystType.ON_CHAIN, asset=f"A{i}", network=f"n{i}")
        for i in range(6)
    )
    news_result = (analyzed_result(ExternalIntelligenceAnalystType.NEWS_SENTIMENT, symbol=SYMBOL),)

    results = on_chain_results + extra + news_result
    assert len(on_chain_results) + len(extra) == 10

    result = ExternalIntelligenceSupervisor().aggregate(results, analysis_time=NOW)

    # Two analyzed TYPES (ON_CHAIN, NEWS_SENTIMENT), not eleven votes.
    assert result.analyzed_analyst_types == (
        ExternalIntelligenceAnalystType.NEWS_SENTIMENT,
        ExternalIntelligenceAnalystType.ON_CHAIN,
    )
    assert result.outcome is ExternalIntelligenceSupervisorOutcome.PARTIAL
    assert result.total_input_results == 11
    assert result.total_analyzed_results == 11


def test_second_news_scope_does_not_change_outcome() -> None:
    results = (
        analyzed_result(ExternalIntelligenceAnalystType.NEWS_SENTIMENT, symbol=SYMBOL),
        analyzed_result(ExternalIntelligenceAnalystType.NEWS_SENTIMENT, symbol=OTHER_SYMBOL),
    )
    result = ExternalIntelligenceSupervisor().aggregate(results, analysis_time=NOW)
    assert result.analyzed_analyst_types == (ExternalIntelligenceAnalystType.NEWS_SENTIMENT,)
    assert result.total_input_results == 2
    assert result.overall_quality is FeatureQuality.VALID
