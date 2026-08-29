"""Stage 4G duplicate-identity tests.

Identity = ``(analyst_type, native_scope)``. Two results sharing an identity
are always a caller/orchestration error - whether their content is
identical or divergent. No last-write-wins, no quality/timestamp
preference, no silent deduplication. Distinct scopes under one analyst type
remain valid and are both retained.
"""

from __future__ import annotations

import pytest

from app.core.enums.external_intelligence_analysis import ExternalIntelligenceAnalystType
from app.core.enums.quality import FeatureQuality
from app.external_intelligence_supervisor.errors import DuplicateAnalystScopeResultError
from app.external_intelligence_supervisor.supervisor import ExternalIntelligenceSupervisor
from tests.external_intelligence_supervisor_support import NOW, OTHER_CURRENCY, OTHER_SYMBOL, analyzed_result


def test_exact_duplicate_is_rejected() -> None:
    result = analyzed_result(ExternalIntelligenceAnalystType.MACRO_EVENT)
    with pytest.raises(DuplicateAnalystScopeResultError):
        ExternalIntelligenceSupervisor().aggregate((result, result), analysis_time=NOW)


def test_divergent_same_identity_duplicate_is_rejected() -> None:
    first = analyzed_result(ExternalIntelligenceAnalystType.MACRO_EVENT, quality=FeatureQuality.VALID)
    second = analyzed_result(ExternalIntelligenceAnalystType.MACRO_EVENT, quality=FeatureQuality.STALE, value="OTHER")
    with pytest.raises(DuplicateAnalystScopeResultError):
        ExternalIntelligenceSupervisor().aggregate((first, second), analysis_time=NOW)


def test_same_analyst_different_scope_is_accepted() -> None:
    usd = analyzed_result(ExternalIntelligenceAnalystType.MACRO_EVENT)
    eur = analyzed_result(ExternalIntelligenceAnalystType.MACRO_EVENT, currency=OTHER_CURRENCY)
    result = ExternalIntelligenceSupervisor().aggregate((usd, eur), analysis_time=NOW)
    assert result.total_input_results == 2
    assert {s.currency for s in result.scope_summaries} == {usd.currency, eur.currency}


def test_multiple_scopes_are_all_retained() -> None:
    btc_news = analyzed_result(ExternalIntelligenceAnalystType.NEWS_SENTIMENT)
    eth_news = analyzed_result(ExternalIntelligenceAnalystType.NEWS_SENTIMENT, symbol=OTHER_SYMBOL)
    result = ExternalIntelligenceSupervisor().aggregate((btc_news, eth_news), analysis_time=NOW)
    assert len(result.analysis_results) == 2
    assert len(result.scope_summaries) == 2
