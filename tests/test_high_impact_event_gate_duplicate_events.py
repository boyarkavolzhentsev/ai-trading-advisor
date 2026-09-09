"""Deterministic handling of multiple provider records at the same
``event_time`` (Calendar Bridge mapping closure, section 3: e.g. CPI mm + yy
both resolve to ``US_CPI`` and are naturally emitted at the same
scheduled instant). No fuzzy deduplication - both records are preserved and
the gate's worst-of-verdict aggregation stays deterministic."""

from __future__ import annotations

from datetime import timedelta

from app.core.enums.high_impact_event import HighImpactEventVerdict
from app.core.enums.strategy_router import StrategyFamily
from app.decision.high_impact_event_gate import HighImpactEventGate
from tests.high_impact_event_support import EVENT_TIME, constructed_setup_result, fresh_context, record, usd_context


def _trend_following(setup_result, context, as_of):
    result = HighImpactEventGate().evaluate(strategy_setup_result=setup_result, context=context, as_of=as_of)
    return next(r for r in result.family_results if r.family is StrategyFamily.TREND_FOLLOWING)


def _same_timestamp_events():
    return (
        record(event_code="US_CPI", event_time=EVENT_TIME, provider_event_id="840030005:277491", name="CPI mm"),
        record(event_code="US_CPI", event_time=EVENT_TIME, provider_event_id="840030007:277515", name="CPI yy"),
    )


def test_both_same_timestamp_records_are_preserved_not_deduplicated() -> None:
    as_of = EVENT_TIME - timedelta(minutes=1)
    setup = constructed_setup_result(context=usd_context(), as_of=as_of)
    ctx = fresh_context(events=_same_timestamp_events(), as_of=as_of)

    family = _trend_following(setup, ctx, as_of)

    assert len(family.relevant_events) == 2
    assert family.verdict is HighImpactEventVerdict.BLOCKED


def test_same_timestamp_relevant_events_are_ordered_by_provider_event_id() -> None:
    as_of = EVENT_TIME - timedelta(minutes=1)
    setup = constructed_setup_result(context=usd_context(), as_of=as_of)
    ctx = fresh_context(events=_same_timestamp_events(), as_of=as_of)

    family = _trend_following(setup, ctx, as_of)

    ids = [event.provider_event_id for event in family.relevant_events]
    assert ids == sorted(ids)


def test_same_timestamp_duplicate_evaluation_is_deterministic() -> None:
    as_of = EVENT_TIME - timedelta(minutes=1)
    setup = constructed_setup_result(context=usd_context(), as_of=as_of)
    ctx = fresh_context(events=_same_timestamp_events(), as_of=as_of)

    first = HighImpactEventGate().evaluate(strategy_setup_result=setup, context=ctx, as_of=as_of)
    second = HighImpactEventGate().evaluate(strategy_setup_result=setup, context=ctx, as_of=as_of)
    assert first == second


def test_next_safe_time_is_the_single_shared_block_end_not_duplicated() -> None:
    """Both records share event_time, so both produce the identical
    BLOCK-window end - next_safe_time must resolve to that one instant,
    not fork into two different values."""
    as_of = EVENT_TIME - timedelta(minutes=1)
    setup = constructed_setup_result(context=usd_context(), as_of=as_of)
    ctx = fresh_context(events=_same_timestamp_events(), as_of=as_of)

    family = _trend_following(setup, ctx, as_of)

    assert family.next_safe_time == EVENT_TIME + timedelta(minutes=5)
