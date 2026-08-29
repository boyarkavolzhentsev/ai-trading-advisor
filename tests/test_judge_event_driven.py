"""Stage 6B EVENT_DRIVEN semantic rules: NEWS_SENTIMENT's
PER_PROVIDER_SENTIMENT_SIGN gated by SENTIMENT_PROVIDER_AGREEMENT is the
only usable PRIMARY evidence - MACRO_EVENT/RATES_YIELD/ON_CHAIN evidence
must never create a direction."""

from __future__ import annotations

from app.core.enums.external_intelligence_analysis import ExternalIntelligenceAnalystType
from app.core.enums.strategy_judge import DirectionalCandidate, JudgeOutcome
from app.core.enums.strategy_router import StrategyFamily
from app.external_intelligence_supervisor.supervisor import ExternalIntelligenceSupervisor
from tests.external_intelligence_supervisor_support import analyzed_result as ext_analyzed_result
from tests.market_evaluation_support import CURRENCY, make_context
from tests.strategy_judge_support import NOW, SYMBOL, external_with_news_sentiment, route_and_judge


def _event_driven_result(judge_result):
    matches = [r for r in judge_result.family_results if r.family is StrategyFamily.EVENT_DRIVEN]
    return matches[0] if matches else None


def test_all_agree_positive_sentiment_is_directional_long() -> None:
    external = external_with_news_sentiment(provider_signs={"providerA": "POSITIVE", "providerB": "POSITIVE"})
    _, judge_result = route_and_judge(external=external, context=make_context())
    result = _event_driven_result(judge_result)
    assert result.outcome is JudgeOutcome.DIRECTIONAL
    assert result.direction is DirectionalCandidate.LONG_CANDIDATE


def test_all_agree_negative_sentiment_is_directional_short() -> None:
    external = external_with_news_sentiment(provider_signs={"providerA": "NEGATIVE", "providerB": "NEGATIVE"})
    _, judge_result = route_and_judge(external=external, context=make_context())
    result = _event_driven_result(judge_result)
    assert result.outcome is JudgeOutcome.DIRECTIONAL
    assert result.direction is DirectionalCandidate.SHORT_CANDIDATE


def test_conflicting_provider_signs_is_mixed() -> None:
    external = external_with_news_sentiment(provider_signs={"providerA": "POSITIVE", "providerB": "NEGATIVE"})
    _, judge_result = route_and_judge(external=external, context=make_context())
    result = _event_driven_result(judge_result)
    assert result.outcome is JudgeOutcome.MIXED
    assert result.direction is None
    assert len(result.evidence_refs) >= 2


def test_no_relevant_news_items_is_insufficient() -> None:
    """Default NEWS_SENTIMENT fixture (RELEVANT_ITEM_PRESENCE only, no
    sentiment agreement dimension at all) must yield INSUFFICIENT_EVIDENCE."""
    external = ExternalIntelligenceSupervisor().aggregate(
        (ext_analyzed_result(ExternalIntelligenceAnalystType.NEWS_SENTIMENT, analysis_time=NOW, symbol=SYMBOL),), analysis_time=NOW
    )
    _, judge_result = route_and_judge(external=external, context=make_context())
    result = _event_driven_result(judge_result)
    assert result.outcome is JudgeOutcome.INSUFFICIENT_EVIDENCE
    assert result.direction is None
    assert result.evidence_refs == ()


def test_unaligned_news_sentiment_is_insufficient() -> None:
    """A NEWS_SENTIMENT scope for a different symbol never aligns - EVENT_DRIVEN
    stays ineligible at Router, so it is simply absent from Judge's output."""
    external = external_with_news_sentiment(symbol="ETHUSDT", provider_signs={"providerA": "POSITIVE"})
    router_result, judge_result = route_and_judge(external=external, context=make_context(symbol="BTCUSDT"))
    assert StrategyFamily.EVENT_DRIVEN not in router_result.eligible_families
    assert _event_driven_result(judge_result) is None


def test_macro_event_only_cannot_create_direction() -> None:
    """Strong MACRO_EVENT surprise evidence alone (no NEWS_SENTIMENT at all)
    must never produce a directional EVENT_DRIVEN verdict."""
    external = ExternalIntelligenceSupervisor().aggregate(
        (ext_analyzed_result(ExternalIntelligenceAnalystType.MACRO_EVENT, analysis_time=NOW, currency=CURRENCY, value="ABOVE_FORECAST"),),
        analysis_time=NOW,
    )
    context = make_context(currency_exposures=(CURRENCY,))
    router_result, judge_result = route_and_judge(external=external, context=context)
    result = _event_driven_result(judge_result)
    if result is not None:
        assert result.outcome is JudgeOutcome.INSUFFICIENT_EVIDENCE
        assert result.direction is None


def test_rates_yield_only_cannot_create_direction() -> None:
    external = ExternalIntelligenceSupervisor().aggregate(
        (ext_analyzed_result(ExternalIntelligenceAnalystType.RATES_YIELD, analysis_time=NOW, currency=CURRENCY, value="RISING"),),
        analysis_time=NOW,
    )
    context = make_context(currency_exposures=(CURRENCY,))
    _, judge_result = route_and_judge(external=external, context=context)
    result = _event_driven_result(judge_result)
    if result is not None:
        assert result.outcome is JudgeOutcome.INSUFFICIENT_EVIDENCE
        assert result.direction is None


def test_on_chain_only_cannot_create_direction() -> None:
    from tests.market_evaluation_support import ASSET, NETWORK

    external = ExternalIntelligenceSupervisor().aggregate(
        (ext_analyzed_result(ExternalIntelligenceAnalystType.ON_CHAIN, analysis_time=NOW, asset=ASSET, network=NETWORK, value="NET_INFLOW"),),
        analysis_time=NOW,
    )
    context = make_context(base_asset=ASSET, network=NETWORK)
    _, judge_result = route_and_judge(external=external, context=context)
    result = _event_driven_result(judge_result)
    if result is not None:
        assert result.outcome is JudgeOutcome.INSUFFICIENT_EVIDENCE
        assert result.direction is None
