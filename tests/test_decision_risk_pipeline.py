"""Decision/Risk Pipeline behavioral tests (Final Runtime Integration, Part C).

Builds real per-family Stage 5 inputs and runs them through the real
``evaluate_decision_risk_pipeline`` - never a hand-rolled pipeline result -
then asserts against the exact same downstream contracts Setup Construction/
Risk Gate/Portfolio Supervisor/Session Gate's own test suites already verify
independently. This module never re-derives any stage's own arithmetic; it
only proves the orchestrator forwards typed results correctly and applies
the one approved fail-closed branch.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.core.enums.decision_risk_pipeline import DecisionRiskPipelineOutcome
from app.core.enums.policy_gate import PolicyFamilyVerdict
from app.core.enums.portfolio import PortfolioBlockReason, PortfolioFamilyVerdict
from app.core.enums.risk_gate import RiskBlockReason, RiskFamilyVerdict
from app.core.enums.session import TradingSessionStatus
from app.core.enums.session_gate import SessionBlockReason, SessionFamilyVerdict
from app.core.enums.setup_construction import SetupBlockReason, SetupConstructionOutcome
from app.core.enums.strategy_router import StrategyFamily
from app.orchestration.decision_risk_pipeline import evaluate_decision_risk_pipeline
from tests.decision_risk_pipeline_support import (
    NOW,
    blocked_assembly,
    context,
    ready_assembly,
    symbol_facts,
    trend_following_market_structure,
    trend_following_technical,
)
from tests.market_evaluation_support import full_flow_result
from tests.risk_gate_support import default_config
from tests.runtime_fact_assembly_support import rollover_ready, usable_open_risk, usable_realized_pnl
from tests.setup_construction_support import result_for
from tests.strategy_judge_support import external_with_news_sentiment


# --- A: happy path ---


def test_happy_path_trend_following_completes() -> None:
    result = evaluate_decision_risk_pipeline(
        flow=None,
        technical=trend_following_technical(),
        external=None,
        context=context(),
        evaluation_time=NOW,
        symbol_facts=symbol_facts(),
        m15_market_structure=trend_following_market_structure(),
        account_risk_snapshot_assembly=ready_assembly(),
        trading_cycle_config=default_config(),
    )

    assert result.outcome is DecisionRiskPipelineOutcome.COMPLETED
    assert result.strategy_session_result is not None

    trend_setup = result_for(result.strategy_setup_result, StrategyFamily.TREND_FOLLOWING)
    assert trend_setup is not None
    assert trend_setup.outcome is SetupConstructionOutcome.CONSTRUCTED

    session_result = result.strategy_session_result
    trend_session = next(r for r in session_result.family_results if r.family is StrategyFamily.TREND_FOLLOWING)
    assert trend_session.verdict is SessionFamilyVerdict.ELIGIBLE_FOR_RUNTIME_REVIEW
    assert trend_session.session_allocated_risk is not None
    assert trend_session.session_allocated_risk > 0


# --- C: Runtime Fact Assembly BLOCKED ---


def test_blocked_assembly_stops_before_risk_and_preserves_reasons() -> None:
    assembly = blocked_assembly()
    result = evaluate_decision_risk_pipeline(
        flow=None,
        technical=trend_following_technical(),
        external=None,
        context=context(),
        evaluation_time=NOW,
        symbol_facts=symbol_facts(),
        m15_market_structure=trend_following_market_structure(),
        account_risk_snapshot_assembly=assembly,
        trading_cycle_config=default_config(),
    )

    assert result.outcome is DecisionRiskPipelineOutcome.BLOCKED_BEFORE_RISK
    assert result.strategy_session_result is None
    assert result.account_risk_snapshot_assembly is assembly
    assert result.account_risk_snapshot_assembly.reasons == assembly.reasons

    trend_setup = result_for(result.strategy_setup_result, StrategyFamily.TREND_FOLLOWING)
    assert trend_setup is not None
    assert trend_setup.outcome is SetupConstructionOutcome.CONSTRUCTED


# --- D: READY assembly - exact AccountRiskSnapshot passed unchanged ---


def test_ready_assembly_account_snapshot_passed_unchanged_into_risk_gate() -> None:
    assembly = ready_assembly()
    result = evaluate_decision_risk_pipeline(
        flow=None,
        technical=trend_following_technical(),
        external=None,
        context=context(),
        evaluation_time=NOW,
        symbol_facts=symbol_facts(),
        m15_market_structure=trend_following_market_structure(),
        account_risk_snapshot_assembly=assembly,
        trading_cycle_config=default_config(),
    )

    risk_result = result.strategy_session_result.strategy_portfolio_result.strategy_risk_result
    assert risk_result.account_snapshot is assembly.account_snapshot


# --- E: Setup bridge ---


def test_setup_bridge_preserves_exact_risk_per_unit_and_zero_sentinel_for_blocked() -> None:
    result = evaluate_decision_risk_pipeline(
        flow=full_flow_result(),
        technical=trend_following_technical(),
        external=external_with_news_sentiment(provider_signs={"provider_a": "POSITIVE", "provider_b": "POSITIVE"}),
        context=context(),
        evaluation_time=NOW,
        symbol_facts=symbol_facts(),
        m15_market_structure=trend_following_market_structure(),
        account_risk_snapshot_assembly=ready_assembly(),
        trading_cycle_config=default_config(),
    )

    setup_result = result.strategy_setup_result
    trend_setup = result_for(setup_result, StrategyFamily.TREND_FOLLOWING)
    event_setup = result_for(setup_result, StrategyFamily.EVENT_DRIVEN)
    assert trend_setup.outcome is SetupConstructionOutcome.CONSTRUCTED
    assert event_setup.outcome is SetupConstructionOutcome.BLOCKED
    assert event_setup.reasons == (SetupBlockReason.FAMILY_SETUP_UNAVAILABLE,)

    risk_result = result.strategy_session_result.strategy_portfolio_result.strategy_risk_result
    trend_candidate = next(c for c in risk_result.candidate_inputs if c.family is StrategyFamily.TREND_FOLLOWING)
    event_candidate = next(c for c in risk_result.candidate_inputs if c.family is StrategyFamily.EVENT_DRIVEN)
    assert trend_candidate.risk_per_unit == trend_setup.setup.risk_per_unit
    assert event_candidate.risk_per_unit == Decimal("0")

    event_risk = next(r for r in risk_result.family_results if r.family is StrategyFamily.EVENT_DRIVEN)
    assert event_risk.verdict is RiskFamilyVerdict.BLOCKED_BY_RISK
    assert RiskBlockReason.ZERO_OR_NEGATIVE_RISK_PER_UNIT in event_risk.reasons


# --- F: no eligible strategy ---


def test_no_market_data_propagates_without_orchestrator_fabrication() -> None:
    result = evaluate_decision_risk_pipeline(
        flow=None,
        technical=None,
        external=None,
        context=context(),
        evaluation_time=NOW,
        symbol_facts=None,
        m15_market_structure=None,
        account_risk_snapshot_assembly=ready_assembly(),
        trading_cycle_config=default_config(),
    )

    assert result.outcome is DecisionRiskPipelineOutcome.COMPLETED
    assert result.strategy_setup_result.family_results == ()

    session_result = result.strategy_session_result
    assert session_result.family_results == ()
    assert session_result.strategy_portfolio_result.family_results == ()
    risk_result = session_result.strategy_portfolio_result.strategy_risk_result
    assert risk_result.family_results == ()
    assert risk_result.candidate_inputs == ()


# --- G: Policy all blocked ---


def test_policy_all_blocked_no_orchestrator_fabricated_candidate() -> None:
    result = evaluate_decision_risk_pipeline(
        flow=None,
        technical=trend_following_technical(return_direction=None, slope_direction=None),
        external=None,
        context=context(),
        evaluation_time=NOW,
        symbol_facts=symbol_facts(),
        m15_market_structure=trend_following_market_structure(),
        account_risk_snapshot_assembly=ready_assembly(),
        trading_cycle_config=default_config(),
    )

    assert result.outcome is DecisionRiskPipelineOutcome.COMPLETED
    policy_result = result.strategy_setup_result.strategy_policy_result
    assert policy_result.family_results
    assert all(r.verdict is PolicyFamilyVerdict.BLOCKED for r in policy_result.family_results)
    assert result.strategy_setup_result.family_results == ()

    risk_result = result.strategy_session_result.strategy_portfolio_result.strategy_risk_result
    assert risk_result.candidate_inputs == ()
    assert all(r.verdict is RiskFamilyVerdict.BLOCKED_BY_RISK for r in risk_result.family_results)
    assert all(RiskBlockReason.POLICY_NOT_ELIGIBLE in r.reasons for r in risk_result.family_results)


# --- H: Risk blocked ---


def test_risk_blocked_propagates_to_portfolio_and_session() -> None:
    assembly = ready_assembly(realized_daily_pnl_assessment=usable_realized_pnl(realized_daily_pnl=Decimal("-5000")))
    result = evaluate_decision_risk_pipeline(
        flow=None,
        technical=trend_following_technical(),
        external=None,
        context=context(),
        evaluation_time=NOW,
        symbol_facts=symbol_facts(),
        m15_market_structure=trend_following_market_structure(),
        account_risk_snapshot_assembly=assembly,
        trading_cycle_config=default_config(),
    )

    risk_result = result.strategy_session_result.strategy_portfolio_result.strategy_risk_result
    trend_risk = next(r for r in risk_result.family_results if r.family is StrategyFamily.TREND_FOLLOWING)
    assert trend_risk.verdict is RiskFamilyVerdict.BLOCKED_BY_RISK
    assert RiskBlockReason.DAILY_LOSS_LIMIT_REACHED in trend_risk.reasons

    portfolio_result = result.strategy_session_result.strategy_portfolio_result
    trend_portfolio = next(r for r in portfolio_result.family_results if r.family is StrategyFamily.TREND_FOLLOWING)
    assert trend_portfolio.verdict is PortfolioFamilyVerdict.BLOCKED_BY_PORTFOLIO
    assert trend_portfolio.reasons == (PortfolioBlockReason.RISK_NOT_ELIGIBLE,)

    session_result = result.strategy_session_result
    trend_session = next(r for r in session_result.family_results if r.family is StrategyFamily.TREND_FOLLOWING)
    assert trend_session.verdict is SessionFamilyVerdict.BLOCKED_BY_SESSION
    assert trend_session.reasons == (SessionBlockReason.PORTFOLIO_NOT_ELIGIBLE,)


# --- I: Portfolio blocked ---


def test_portfolio_blocked_propagates_exact_result_to_session() -> None:
    config = default_config(portfolio_risk_limit_percent=Decimal("0.1"), per_trade_risk_limit_percent=Decimal("0.05"))
    assembly = ready_assembly(open_risk_assessment=usable_open_risk(current_open_risk_to_stop=Decimal("150")))
    result = evaluate_decision_risk_pipeline(
        flow=None,
        technical=trend_following_technical(),
        external=None,
        context=context(),
        evaluation_time=NOW,
        symbol_facts=symbol_facts(),
        m15_market_structure=trend_following_market_structure(),
        account_risk_snapshot_assembly=assembly,
        trading_cycle_config=config,
    )

    risk_result = result.strategy_session_result.strategy_portfolio_result.strategy_risk_result
    trend_risk = next(r for r in risk_result.family_results if r.family is StrategyFamily.TREND_FOLLOWING)
    assert trend_risk.verdict is RiskFamilyVerdict.ELIGIBLE_FOR_PORTFOLIO_REVIEW

    portfolio_result = result.strategy_session_result.strategy_portfolio_result
    trend_portfolio = next(r for r in portfolio_result.family_results if r.family is StrategyFamily.TREND_FOLLOWING)
    assert trend_portfolio.verdict is PortfolioFamilyVerdict.BLOCKED_BY_PORTFOLIO
    assert trend_portfolio.reasons == (PortfolioBlockReason.GLOBAL_PORTFOLIO_CAP_REACHED,)

    session_result = result.strategy_session_result
    trend_session = next(r for r in session_result.family_results if r.family is StrategyFamily.TREND_FOLLOWING)
    assert trend_session.verdict is SessionFamilyVerdict.BLOCKED_BY_SESSION
    assert trend_session.reasons == (SessionBlockReason.PORTFOLIO_NOT_ELIGIBLE,)


# --- J: Session LOCKED / non-actionable state, pipeline still COMPLETED ---


def test_session_locked_override_remains_completed_with_blocked_family() -> None:
    result = evaluate_decision_risk_pipeline(
        flow=None,
        technical=trend_following_technical(),
        external=None,
        context=context(),
        evaluation_time=NOW,
        symbol_facts=symbol_facts(),
        m15_market_structure=trend_following_market_structure(),
        account_risk_snapshot_assembly=ready_assembly(),
        trading_cycle_config=default_config(),
        locked_override=True,
    )

    assert result.outcome is DecisionRiskPipelineOutcome.COMPLETED
    session_result = result.strategy_session_result
    assert session_result.session_status is TradingSessionStatus.LOCKED
    trend_session = next(r for r in session_result.family_results if r.family is StrategyFamily.TREND_FOLLOWING)
    assert trend_session.verdict is SessionFamilyVerdict.BLOCKED_BY_SESSION
    assert trend_session.reasons == (SessionBlockReason.SESSION_LOCKED,)


# --- L: timestamp ---


def test_caller_supplied_evaluation_time_propagates_with_no_wall_clock_substitution() -> None:
    custom_time = datetime(2027, 6, 1, 8, 30, 0, tzinfo=UTC)
    assembly = ready_assembly(
        as_of=custom_time,
        rollover_snapshot=rollover_ready(as_of=custom_time),
        realized_daily_pnl_assessment=usable_realized_pnl(as_of=custom_time),
        open_risk_assessment=usable_open_risk(as_of=custom_time),
    )
    result = evaluate_decision_risk_pipeline(
        flow=None,
        technical=trend_following_technical(),
        external=None,
        context=context(),
        evaluation_time=custom_time,
        symbol_facts=symbol_facts(),
        m15_market_structure=trend_following_market_structure(),
        account_risk_snapshot_assembly=assembly,
        trading_cycle_config=default_config(),
    )

    market_evaluation = (
        result.strategy_setup_result.strategy_policy_result.strategy_judge_result.strategy_router_result.market_evaluation
    )
    assert market_evaluation.evaluation_time == custom_time

    trend_setup = result_for(result.strategy_setup_result, StrategyFamily.TREND_FOLLOWING)
    assert trend_setup.setup.signal_time == custom_time


# --- N: determinism ---


def test_determinism_same_inputs_produce_equal_outputs() -> None:
    kwargs = dict(
        flow=None,
        technical=trend_following_technical(),
        external=None,
        context=context(),
        evaluation_time=NOW,
        symbol_facts=symbol_facts(),
        m15_market_structure=trend_following_market_structure(),
        account_risk_snapshot_assembly=ready_assembly(),
        trading_cycle_config=default_config(),
    )
    first = evaluate_decision_risk_pipeline(**kwargs)
    second = evaluate_decision_risk_pipeline(**kwargs)
    assert first == second
