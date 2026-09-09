"""Narrow FOMC MODERATE hard-block eligibility exception (Calendar Bridge
FOMC policy closure) - required matrix:

- FOMC MODERATE blocks
- FOMC HIGH blocks
- US_NFP MODERATE does not hard-block
- US_CPI MODERATE does not hard-block
- US_GDP/US_ISM/US_MAJOR_PMI remain WARN-only regardless of importance

No generalized importance relaxation: every other hard-block canonical code
keeps the implicit HIGH-only minimum.
"""

from __future__ import annotations

from datetime import timedelta

from app.core.enums.high_impact_event import HighImpactEventVerdict
from app.core.enums.strategy_router import StrategyFamily
from app.decision.high_impact_event_gate import HighImpactEventGate
from tests.high_impact_event_support import EVENT_TIME, constructed_setup_result, fresh_context, record, usd_context


def _trend_following(setup_result, context, as_of):
    result = HighImpactEventGate().evaluate(strategy_setup_result=setup_result, context=context, as_of=as_of)
    return next(r for r in result.family_results if r.family is StrategyFamily.TREND_FOLLOWING)


def _verdict_at_block_time(*, event_code: str, importance: str, context=None) -> HighImpactEventVerdict:
    as_of = EVENT_TIME - timedelta(minutes=1)  # deep inside the BLOCK window
    market_context = context if context is not None else usd_context()
    setup = constructed_setup_result(context=market_context, as_of=as_of)
    ctx = fresh_context(events=(record(event_code=event_code, event_time=EVENT_TIME, importance=importance),), as_of=as_of)
    return _trend_following(setup, ctx, as_of).verdict


def test_fomc_moderate_blocks() -> None:
    assert _verdict_at_block_time(event_code="FOMC", importance="MODERATE") is HighImpactEventVerdict.BLOCKED


def test_fomc_high_blocks() -> None:
    assert _verdict_at_block_time(event_code="FOMC", importance="HIGH") is HighImpactEventVerdict.BLOCKED


def test_us_nfp_moderate_does_not_hard_block() -> None:
    assert _verdict_at_block_time(event_code="US_NFP", importance="MODERATE") is HighImpactEventVerdict.WARNED


def test_us_cpi_moderate_does_not_hard_block() -> None:
    assert _verdict_at_block_time(event_code="US_CPI", importance="MODERATE") is HighImpactEventVerdict.WARNED


def test_us_gdp_moderate_remains_warn_only() -> None:
    assert _verdict_at_block_time(event_code="US_GDP", importance="MODERATE") is HighImpactEventVerdict.WARNED


def test_us_gdp_high_remains_warn_only_never_blocks() -> None:
    assert _verdict_at_block_time(event_code="US_GDP", importance="HIGH") is HighImpactEventVerdict.WARNED


def test_us_ism_high_remains_warn_only_never_blocks() -> None:
    assert _verdict_at_block_time(event_code="US_ISM", importance="HIGH") is HighImpactEventVerdict.WARNED


def test_us_major_pmi_high_remains_warn_only_never_blocks() -> None:
    assert _verdict_at_block_time(event_code="US_MAJOR_PMI", importance="HIGH") is HighImpactEventVerdict.WARNED


def test_ecb_rate_decision_moderate_does_not_hard_block() -> None:
    """No generalized relaxation: only FOMC gets the MODERATE override."""
    assert _verdict_at_block_time(event_code="ECB_RATE_DECISION", importance="MODERATE") is HighImpactEventVerdict.WARNED


def test_boe_rate_decision_moderate_does_not_hard_block() -> None:
    context = usd_context(currency_exposures=("GBP", "USD"))
    assert _verdict_at_block_time(event_code="BOE_RATE_DECISION", importance="MODERATE", context=context) is HighImpactEventVerdict.WARNED
