"""Pins the approved Stage 6A finding: ``TREND_FOLLOWING`` and
``MEAN_REVERSION`` share an identical V1 structural eligibility rule.

Any future divergence between the two must be a deliberate code change that
also updates this test, never silent drift - their semantic distinction is
Stage 6B Judge's, from dimension/value content Stage 6A never reads.
"""

from __future__ import annotations

import pytest

from app.core.enums.quality import FeatureQuality
from app.core.enums.strategy_router import StrategyFamily
from app.strategies.router import StrategyRouter
from tests.market_evaluation_support import full_technical_result, insufficient_technical_result
from tests.strategy_router_support import evaluation, technical_result_with_quality

FIXTURES = [
    None,
    insufficient_technical_result(),
    technical_result_with_quality(FeatureQuality.VALID),
    technical_result_with_quality(FeatureQuality.PARTIAL),
    technical_result_with_quality(FeatureQuality.STALE),
    technical_result_with_quality(FeatureQuality.UNAVAILABLE),
    full_technical_result(),
]


@pytest.mark.parametrize("technical", FIXTURES, ids=lambda t: "None" if t is None else t.outcome.value)
def test_trend_following_and_mean_reversion_agree(technical) -> None:
    result = StrategyRouter().route(market_evaluation=evaluation(technical=technical))
    entries = {entry.family: entry for entry in result.eligibility}
    trend = entries[StrategyFamily.TREND_FOLLOWING]
    reversion = entries[StrategyFamily.MEAN_REVERSION]
    assert trend.eligible == reversion.eligible
    assert trend.ineligibility_reasons == reversion.ineligibility_reasons
