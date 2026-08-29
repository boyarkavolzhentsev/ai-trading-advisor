"""Stage 4G native-scope preservation tests.

Each ``ExternalIntelligenceScopeSummary`` must mirror its analyst type's
Stage 4F scope shape exactly: Macro/Rates carry currency only, News carries
symbol only, On-Chain carries asset+network only.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.enums.external_intelligence_analysis import ExternalIntelligenceAnalystType, ExternalIntelligenceOutcome
from app.core.enums.quality import FeatureQuality
from app.core.models.external_intelligence_supervisor_result import ExternalIntelligenceScopeSummary
from app.external_intelligence_supervisor.supervisor import ExternalIntelligenceSupervisor
from tests.external_intelligence_supervisor_support import ASSET, CURRENCY, NETWORK, NOW, SYMBOL, analyzed_result


def test_macro_event_scope_is_currency_only() -> None:
    result = ExternalIntelligenceSupervisor().aggregate(
        (analyzed_result(ExternalIntelligenceAnalystType.MACRO_EVENT),), analysis_time=NOW
    )
    summary = result.scope_summaries[0]
    assert summary.currency == CURRENCY
    assert summary.symbol is None
    assert summary.asset is None
    assert summary.network is None


def test_rates_yield_scope_is_currency_only() -> None:
    result = ExternalIntelligenceSupervisor().aggregate(
        (analyzed_result(ExternalIntelligenceAnalystType.RATES_YIELD),), analysis_time=NOW
    )
    summary = result.scope_summaries[0]
    assert summary.currency == CURRENCY
    assert summary.symbol is None
    assert summary.asset is None
    assert summary.network is None


def test_news_sentiment_scope_is_symbol_only() -> None:
    result = ExternalIntelligenceSupervisor().aggregate(
        (analyzed_result(ExternalIntelligenceAnalystType.NEWS_SENTIMENT),), analysis_time=NOW
    )
    summary = result.scope_summaries[0]
    assert summary.symbol == SYMBOL
    assert summary.currency is None
    assert summary.asset is None
    assert summary.network is None


def test_on_chain_scope_is_asset_and_network_only() -> None:
    result = ExternalIntelligenceSupervisor().aggregate(
        (analyzed_result(ExternalIntelligenceAnalystType.ON_CHAIN),), analysis_time=NOW
    )
    summary = result.scope_summaries[0]
    assert summary.asset == ASSET
    assert summary.network == NETWORK
    assert summary.currency is None
    assert summary.symbol is None


def _summary(**overrides: object) -> dict[str, object]:
    fields: dict[str, object] = {
        "analyst_type": ExternalIntelligenceAnalystType.MACRO_EVENT,
        "currency": CURRENCY,
        "result_outcome": ExternalIntelligenceOutcome.ANALYZED,
        "quality": FeatureQuality.VALID,
        "result_index": 0,
    }
    fields.update(overrides)
    return fields


def test_macro_event_scope_summary_requires_currency() -> None:
    with pytest.raises(ValidationError):
        ExternalIntelligenceScopeSummary(**_summary(currency=None))


def test_macro_event_scope_summary_forbids_symbol() -> None:
    with pytest.raises(ValidationError):
        ExternalIntelligenceScopeSummary(**_summary(symbol=SYMBOL))


def test_news_sentiment_scope_summary_requires_symbol() -> None:
    with pytest.raises(ValidationError):
        ExternalIntelligenceScopeSummary(
            **_summary(analyst_type=ExternalIntelligenceAnalystType.NEWS_SENTIMENT, currency=None)
        )


def test_news_sentiment_scope_summary_forbids_currency() -> None:
    with pytest.raises(ValidationError):
        ExternalIntelligenceScopeSummary(
            **_summary(analyst_type=ExternalIntelligenceAnalystType.NEWS_SENTIMENT, symbol=SYMBOL, currency=CURRENCY)
        )


def test_on_chain_scope_summary_requires_asset_and_network() -> None:
    with pytest.raises(ValidationError):
        ExternalIntelligenceScopeSummary(
            **_summary(analyst_type=ExternalIntelligenceAnalystType.ON_CHAIN, currency=None, asset=ASSET)
        )
    with pytest.raises(ValidationError):
        ExternalIntelligenceScopeSummary(
            **_summary(analyst_type=ExternalIntelligenceAnalystType.ON_CHAIN, currency=None, network=NETWORK)
        )


def test_on_chain_scope_summary_forbids_currency_and_symbol() -> None:
    with pytest.raises(ValidationError):
        ExternalIntelligenceScopeSummary(
            **_summary(
                analyst_type=ExternalIntelligenceAnalystType.ON_CHAIN,
                asset=ASSET,
                network=NETWORK,
                currency=CURRENCY,
            )
        )
