"""``to_event_adjusted_candidate_risk_inputs`` compatibility-bridge tests
(Corrective V1 Integration, test groups Q/R/S/T + E/F from the approved
design report)."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from app.core.enums.strategy_router import StrategyFamily
from app.core.models.risk_gate_result import CandidateRiskInput
from app.decision.high_impact_event_gate import HighImpactEventGate, to_event_adjusted_candidate_risk_inputs
from app.decision.setup_construction import to_candidate_risk_inputs
from tests.high_impact_event_support import (
    EVENT_TIME,
    btc_context,
    constructed_setup_result,
    constructed_setup_result_with_event_driven_blocked,
    fresh_context,
    record,
    usd_context,
)


def test_none_event_result_returns_base_unchanged() -> None:
    as_of = EVENT_TIME - timedelta(minutes=4)
    setup = constructed_setup_result(context=usd_context(), as_of=as_of)

    base = to_candidate_risk_inputs(setup)
    adjusted = to_event_adjusted_candidate_risk_inputs(setup, None)

    assert adjusted == base


def test_event_blocked_family_replaced_with_zero_sentinel() -> None:
    as_of = EVENT_TIME - timedelta(minutes=4)
    setup = constructed_setup_result(context=usd_context(), as_of=as_of)
    ctx = fresh_context(events=(record(event_time=EVENT_TIME),), as_of=as_of)
    event_result = HighImpactEventGate().evaluate(strategy_setup_result=setup, context=ctx, as_of=as_of)

    adjusted = to_event_adjusted_candidate_risk_inputs(setup, event_result)

    tf_candidate = next(c for c in adjusted if c.family is StrategyFamily.TREND_FOLLOWING)
    assert tf_candidate.risk_per_unit == Decimal("0")


def test_family_count_set_and_order_preserved() -> None:
    as_of = EVENT_TIME - timedelta(minutes=4)
    setup = constructed_setup_result_with_event_driven_blocked(context=btc_context(), as_of=as_of)
    ctx = fresh_context(events=(record(event_code="FOMC", event_time=EVENT_TIME),), as_of=as_of)
    event_result = HighImpactEventGate().evaluate(strategy_setup_result=setup, context=ctx, as_of=as_of)

    base = to_candidate_risk_inputs(setup)
    adjusted = to_event_adjusted_candidate_risk_inputs(setup, event_result)

    assert len(adjusted) == len(base)
    assert {c.family for c in adjusted} == {c.family for c in base}
    assert [c.family for c in adjusted] == [c.family for c in base]


def test_setup_blocked_family_existing_zero_sentinel_unchanged() -> None:
    """EVENT_DRIVEN is Setup-BLOCKED (FAMILY_SETUP_UNAVAILABLE) - it never
    gets a HighImpactEventFamilyResult (see test_high_impact_event_gate.py's
    Q test) - its base Decimal('0') sentinel must pass through untouched,
    for the SAME reason it already had, not a reinterpreted event reason."""
    as_of = EVENT_TIME - timedelta(minutes=4)
    setup = constructed_setup_result_with_event_driven_blocked(context=btc_context(), as_of=as_of)
    ctx = fresh_context(events=(record(event_code="FOMC", event_time=EVENT_TIME),), as_of=as_of)
    event_result = HighImpactEventGate().evaluate(strategy_setup_result=setup, context=ctx, as_of=as_of)

    assert {r.family for r in event_result.family_results} == {StrategyFamily.TREND_FOLLOWING}

    base = to_candidate_risk_inputs(setup)
    adjusted = to_event_adjusted_candidate_risk_inputs(setup, event_result)

    base_event_driven = next(c for c in base if c.family is StrategyFamily.EVENT_DRIVEN)
    adjusted_event_driven = next(c for c in adjusted if c.family is StrategyFamily.EVENT_DRIVEN)
    assert base_event_driven == adjusted_event_driven == CandidateRiskInput(family=StrategyFamily.EVENT_DRIVEN, risk_per_unit=Decimal("0"))


def test_never_duplicates_or_reimplements_to_candidate_risk_inputs_logic() -> None:
    """The bridge composes the existing function - it must produce the
    exact same non-blocked entries, never re-derive risk_per_unit itself."""
    as_of = EVENT_TIME + timedelta(minutes=30)  # well clear of any window -> nothing blocked
    setup = constructed_setup_result(context=usd_context(), as_of=as_of)
    ctx = fresh_context(events=(record(event_time=EVENT_TIME),), as_of=as_of)
    event_result = HighImpactEventGate().evaluate(strategy_setup_result=setup, context=ctx, as_of=as_of)

    assert all(r.reasons == () for r in event_result.family_results)

    base = to_candidate_risk_inputs(setup)
    adjusted = to_event_adjusted_candidate_risk_inputs(setup, event_result)
    assert adjusted == base
