"""Setup Construction's approved V1 abstentions: EVENT_DRIVEN and
(defensively) MEAN_REVERSION never get a constructed setup, regardless of
shared-fact availability - and a Policy-blocked family never receives a
``SetupConstructionResult`` at all."""

from __future__ import annotations

from decimal import Decimal

from app.core.enums.setup_construction import SetupBlockReason, SetupConstructionOutcome
from app.core.enums.strategy_router import StrategyFamily
from app.core.enums.technical import SwingKind
from app.decision.setup_construction import SetupConstruction
from tests.setup_construction_support import (
    AS_OF,
    event_driven_policy_result,
    mean_reversion_synthetic_policy_result,
    result_for,
    swing,
    symbol_facts,
    trend_following_policy_result,
    usable_market_structure,
)


def test_event_driven_blocked_family_setup_unavailable_with_facts_present() -> None:
    policy = event_driven_policy_result()
    ms = usable_market_structure(swings=(swing(kind=SwingKind.LOW, price=Decimal("95")),))

    setup_result = SetupConstruction().construct(
        strategy_policy_result=policy, as_of=AS_OF, symbol_facts=symbol_facts(), m15_market_structure=ms
    )
    result = result_for(setup_result, StrategyFamily.EVENT_DRIVEN)

    assert result.outcome is SetupConstructionOutcome.BLOCKED
    assert result.reasons == (SetupBlockReason.FAMILY_SETUP_UNAVAILABLE,)


def test_event_driven_blocked_family_setup_unavailable_with_facts_absent() -> None:
    """Proves EVENT_DRIVEN never even inspects symbol_facts/market_structure
    - both are None here and the outcome/reason is identical either way."""
    policy = event_driven_policy_result()

    setup_result = SetupConstruction().construct(
        strategy_policy_result=policy, as_of=AS_OF, symbol_facts=None, m15_market_structure=None
    )
    result = result_for(setup_result, StrategyFamily.EVENT_DRIVEN)

    assert result.outcome is SetupConstructionOutcome.BLOCKED
    assert result.reasons == (SetupBlockReason.FAMILY_SETUP_UNAVAILABLE,)


def test_mean_reversion_defensive_blocked_family_setup_unavailable() -> None:
    """MEAN_REVERSION can never legitimately reach Policy-eligibility via the
    real ``Judge`` (it always abstains) - this fixture synthesizes a
    Policy-eligible MEAN_REVERSION to prove Setup Construction's own
    defensive handling is correct regardless."""
    policy = mean_reversion_synthetic_policy_result()
    ms = usable_market_structure(swings=(swing(kind=SwingKind.LOW, price=Decimal("95")),))

    setup_result = SetupConstruction().construct(
        strategy_policy_result=policy, as_of=AS_OF, symbol_facts=symbol_facts(), m15_market_structure=ms
    )
    result = result_for(setup_result, StrategyFamily.MEAN_REVERSION)

    assert result.outcome is SetupConstructionOutcome.BLOCKED
    assert result.reasons == (SetupBlockReason.FAMILY_SETUP_UNAVAILABLE,)


def test_policy_blocked_family_receives_no_setup_result() -> None:
    """TREND_FOLLOWING-only eligibility leaves MEAN_REVERSION Policy-BLOCKED
    (JUDGE_OUTCOME_INSUFFICIENT_EVIDENCE) - it must not appear in
    ``family_results`` at all, never as a BLOCKED entry."""
    policy = trend_following_policy_result(direction="UPWARD")

    setup_result = SetupConstruction().construct(
        strategy_policy_result=policy, as_of=AS_OF, symbol_facts=symbol_facts(), m15_market_structure=None
    )

    families = {r.family for r in setup_result.family_results}
    assert StrategyFamily.MEAN_REVERSION not in families
    assert families == {StrategyFamily.TREND_FOLLOWING}
