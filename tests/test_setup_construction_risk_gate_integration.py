"""``to_candidate_risk_inputs`` - the pure compatibility bridge into the
existing, unmodified ``RiskGate`` contract."""

from __future__ import annotations

from decimal import Decimal

from app.core.enums.risk_gate import RiskBlockReason, RiskFamilyVerdict
from app.core.enums.setup_construction import SetupBlockReason
from app.core.enums.strategy_router import StrategyFamily
from app.core.enums.technical import SwingKind
from app.core.models.risk_gate_result import CandidateRiskInput
from app.decision.setup_construction import SetupConstruction, to_candidate_risk_inputs
from app.risk.engine import RiskGate
from tests.risk_gate_support import default_account_snapshot, default_config
from tests.setup_construction_support import AS_OF, result_for, swing, symbol_facts, trend_following_policy_result, usable_market_structure


def test_constructed_setup_bridges_exact_risk_per_unit() -> None:
    policy = trend_following_policy_result(direction="UPWARD")
    ms = usable_market_structure(swings=(swing(kind=SwingKind.LOW, price=Decimal("95")),))
    facts = symbol_facts(ask=Decimal("110"), bid=Decimal("109.5"))
    setup_result = SetupConstruction().construct(strategy_policy_result=policy, as_of=AS_OF, symbol_facts=facts, m15_market_structure=ms)
    setup = result_for(setup_result, StrategyFamily.TREND_FOLLOWING)

    candidates = to_candidate_risk_inputs(setup_result)

    assert candidates == (CandidateRiskInput(family=StrategyFamily.TREND_FOLLOWING, risk_per_unit=setup.setup.risk_per_unit),)


def test_blocked_setup_bridges_zero_sentinel() -> None:
    policy = trend_following_policy_result(direction="UPWARD")
    # No usable structure at all -> BLOCKED / SHARED_FACT_UNAVAILABLE.
    setup_result = SetupConstruction().construct(
        strategy_policy_result=policy, as_of=AS_OF, symbol_facts=symbol_facts(), m15_market_structure=None
    )
    setup = result_for(setup_result, StrategyFamily.TREND_FOLLOWING)
    assert setup.reasons == (SetupBlockReason.SHARED_FACT_UNAVAILABLE,)

    candidates = to_candidate_risk_inputs(setup_result)

    assert candidates == (CandidateRiskInput(family=StrategyFamily.TREND_FOLLOWING, risk_per_unit=Decimal("0")),)


def test_exactly_one_candidate_risk_input_per_policy_eligible_family() -> None:
    policy = trend_following_policy_result(direction="UPWARD")
    setup_result = SetupConstruction().construct(
        strategy_policy_result=policy, as_of=AS_OF, symbol_facts=None, m15_market_structure=None
    )

    candidates = to_candidate_risk_inputs(setup_result)

    assert len(candidates) == len(setup_result.family_results)
    assert {c.family for c in candidates} == {r.family for r in setup_result.family_results}


def test_risk_gate_accepts_bridge_output_without_modification() -> None:
    """RiskGate.evaluate must accept the bridge output as-is - no
    RiskGate/model change was made to support Setup Construction."""
    policy = trend_following_policy_result(direction="UPWARD")
    ms = usable_market_structure(swings=(swing(kind=SwingKind.LOW, price=Decimal("95")),))
    facts = symbol_facts(ask=Decimal("110"), bid=Decimal("109.5"))
    setup_result = SetupConstruction().construct(strategy_policy_result=policy, as_of=AS_OF, symbol_facts=facts, m15_market_structure=ms)

    candidates = to_candidate_risk_inputs(setup_result)
    risk_result = RiskGate().evaluate(
        strategy_policy_result=policy,
        account_snapshot=default_account_snapshot(),
        candidate_inputs=candidates,
        trading_cycle_config=default_config(),
    )

    tf_risk = next(r for r in risk_result.family_results if r.family is StrategyFamily.TREND_FOLLOWING)
    assert tf_risk.verdict is RiskFamilyVerdict.ELIGIBLE_FOR_PORTFOLIO_REVIEW


def test_blocked_setup_reaches_existing_zero_or_negative_risk_per_unit_behavior() -> None:
    policy = trend_following_policy_result(direction="UPWARD")
    setup_result = SetupConstruction().construct(
        strategy_policy_result=policy, as_of=AS_OF, symbol_facts=None, m15_market_structure=None
    )
    setup = result_for(setup_result, StrategyFamily.TREND_FOLLOWING)
    assert setup.reasons == (SetupBlockReason.SHARED_FACT_UNAVAILABLE,)  # the true reason, retained on StrategySetupResult

    candidates = to_candidate_risk_inputs(setup_result)
    risk_result = RiskGate().evaluate(
        strategy_policy_result=policy,
        account_snapshot=default_account_snapshot(),
        candidate_inputs=candidates,
        trading_cycle_config=default_config(),
    )

    tf_risk = next(r for r in risk_result.family_results if r.family is StrategyFamily.TREND_FOLLOWING)
    assert tf_risk.verdict is RiskFamilyVerdict.BLOCKED_BY_RISK
    assert tf_risk.reasons == (RiskBlockReason.ZERO_OR_NEGATIVE_RISK_PER_UNIT,)
    # The zero sentinel is only ever RiskGate's own compatibility reason -
    # never mistaken for the real explanation, which stays on setup_result.
