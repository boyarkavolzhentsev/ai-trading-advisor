"""Decision/Risk Pipeline High-Impact Event Risk Gate integration tests
(Corrective V1 Integration, test groups U/V/W/X/Y/Z).

Runs the real, full ``evaluate_decision_risk_pipeline`` (never a hand-rolled
result) and traces an event-blocked family all the way through Risk ->
Portfolio -> Session -> Final Recommendation, proving it can never become
``ACTIONABLE`` - and that a caller who supplies no High-Impact Event
context sees byte-for-byte unchanged pre-existing behavior.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from app.core.enums.decision_risk_pipeline import DecisionRiskPipelineOutcome
from app.core.enums.final_recommendation import FinalRecommendationVerdict
from app.core.enums.high_impact_event import HighImpactEventDataQuality, HighImpactEventImportance, HighImpactEventVerdict
from app.core.enums.portfolio import PortfolioBlockReason, PortfolioFamilyVerdict
from app.core.enums.risk_gate import RiskBlockReason, RiskFamilyVerdict
from app.core.enums.session_gate import SessionBlockReason, SessionFamilyVerdict
from app.core.enums.strategy_router import StrategyFamily
from app.core.models.high_impact_event import HighImpactEventContext, HighImpactEventRecord
from app.orchestration.decision_risk_pipeline import evaluate_decision_risk_pipeline
from app.orchestration.final_recommendation import construct_final_recommendations
from tests.decision_risk_pipeline_support import NOW, context, ready_assembly, symbol_facts, trend_following_market_structure, trend_following_technical
from tests.final_recommendation_support import actionable_trend_market_structure
from tests.risk_gate_support import default_config

_EVENT_TIME = NOW  # signal_time == evaluation_time == NOW -> deep inside the BLOCK window


def _usd_context(**overrides: object):
    fields: dict[str, object] = {"currency_exposures": ("USD",)}
    fields.update(overrides)
    return context(**fields)


def _blocking_event_context() -> HighImpactEventContext:
    return HighImpactEventContext(
        events=(
            HighImpactEventRecord(
                provider_event_id="1",
                event_time=_EVENT_TIME,
                importance=HighImpactEventImportance.HIGH,
                scope=("USD",),
                event_code="FOMC",
                name="FOMC Rate Decision",
            ),
        ),
        data_quality=HighImpactEventDataQuality.FRESH,
        producer="test_bridge",
        generated_at=NOW,
    )


def _run(*, high_impact_event_context=None, ctx=None):
    return evaluate_decision_risk_pipeline(
        flow=None,
        technical=trend_following_technical(),
        external=None,
        context=ctx if ctx is not None else _usd_context(),
        evaluation_time=NOW,
        symbol_facts=symbol_facts(),
        m15_market_structure=trend_following_market_structure(),
        account_risk_snapshot_assembly=ready_assembly(),
        trading_cycle_config=default_config(),
        high_impact_event_context=high_impact_event_context,
    )


# --- Y: authoritative result always retained ---


def test_high_impact_event_risk_result_retained_in_pipeline_result() -> None:
    result = _run(high_impact_event_context=_blocking_event_context())
    assert result.high_impact_event_risk_result is not None
    tf = next(r for r in result.high_impact_event_risk_result.family_results if r.family is StrategyFamily.TREND_FOLLOWING)
    assert tf.verdict is HighImpactEventVerdict.BLOCKED


def test_high_impact_event_risk_result_retained_even_when_blocked_before_risk() -> None:
    from tests.decision_risk_pipeline_support import blocked_assembly

    result = evaluate_decision_risk_pipeline(
        flow=None,
        technical=trend_following_technical(),
        external=None,
        context=_usd_context(),
        evaluation_time=NOW,
        symbol_facts=symbol_facts(),
        m15_market_structure=trend_following_market_structure(),
        account_risk_snapshot_assembly=blocked_assembly(),
        trading_cycle_config=default_config(),
        high_impact_event_context=_blocking_event_context(),
    )
    assert result.outcome is DecisionRiskPipelineOutcome.BLOCKED_BEFORE_RISK
    assert result.high_impact_event_risk_result is not None


# --- U: RiskGate blocks the event-blocked family ---


def test_risk_gate_blocks_event_blocked_family() -> None:
    result = _run(high_impact_event_context=_blocking_event_context())
    risk_result = result.strategy_session_result.strategy_portfolio_result.strategy_risk_result

    trend_candidate = next(c for c in risk_result.candidate_inputs if c.family is StrategyFamily.TREND_FOLLOWING)
    assert trend_candidate.risk_per_unit == Decimal("0")

    trend_risk = next(r for r in risk_result.family_results if r.family is StrategyFamily.TREND_FOLLOWING)
    assert trend_risk.verdict is RiskFamilyVerdict.BLOCKED_BY_RISK
    assert RiskBlockReason.ZERO_OR_NEGATIVE_RISK_PER_UNIT in trend_risk.reasons


# --- V: Portfolio propagates the block ---


def test_portfolio_propagates_event_block() -> None:
    result = _run(high_impact_event_context=_blocking_event_context())
    portfolio_result = result.strategy_session_result.strategy_portfolio_result
    trend_portfolio = next(r for r in portfolio_result.family_results if r.family is StrategyFamily.TREND_FOLLOWING)
    assert trend_portfolio.verdict is PortfolioFamilyVerdict.BLOCKED_BY_PORTFOLIO
    assert trend_portfolio.reasons == (PortfolioBlockReason.RISK_NOT_ELIGIBLE,)


# --- W: Session propagates the block ---


def test_session_propagates_event_block() -> None:
    result = _run(high_impact_event_context=_blocking_event_context())
    session_result = result.strategy_session_result
    trend_session = next(r for r in session_result.family_results if r.family is StrategyFamily.TREND_FOLLOWING)
    assert trend_session.verdict is SessionFamilyVerdict.BLOCKED_BY_SESSION
    assert trend_session.reasons == (SessionBlockReason.PORTFOLIO_NOT_ELIGIBLE,)


# --- X: Final Recommendation is never ACTIONABLE ---


def test_final_recommendation_never_actionable_for_event_blocked_family() -> None:
    result = _run(high_impact_event_context=_blocking_event_context())
    final_result = construct_final_recommendations(
        decision_risk_pipeline_result=result,
        symbol_facts=symbol_facts(),
        account_currency="USD",
        trade_ids={},
        as_of=NOW,
    )
    trend_final = next(r for r in final_result.family_results if r.family is StrategyFamily.TREND_FOLLOWING)
    assert trend_final.verdict is FinalRecommendationVerdict.BLOCKED


def test_final_recommendation_is_actionable_without_event_block_same_inputs_otherwise() -> None:
    """Control case: the exact same inputs, minus a blocking event, DO
    reach ACTIONABLE - proving the block above is caused by the event, not
    some other unrelated fixture defect. Uses ``actionable_trend_market_structure``
    (a stop close enough to entry that Stage 10C's own broker-volume floor
    never rejects the size) - unlike the plain ``trend_following_market_structure``
    used elsewhere in this file, which is deliberately far and never reaches
    Stage 10C sizing at all."""
    result = evaluate_decision_risk_pipeline(
        flow=None,
        technical=trend_following_technical(),
        external=None,
        context=_usd_context(),
        evaluation_time=NOW,
        symbol_facts=symbol_facts(),
        m15_market_structure=actionable_trend_market_structure(),
        account_risk_snapshot_assembly=ready_assembly(),
        trading_cycle_config=default_config(),
        high_impact_event_context=None,
    )
    final_result = construct_final_recommendations(
        decision_risk_pipeline_result=result,
        symbol_facts=symbol_facts(),
        account_currency="USD",
        trade_ids={StrategyFamily.TREND_FOLLOWING: "trade-1"},
        as_of=NOW,
    )
    trend_final = next(r for r in final_result.family_results if r.family is StrategyFamily.TREND_FOLLOWING)
    assert trend_final.verdict is FinalRecommendationVerdict.ACTIONABLE


# --- Z: no context supplied -> byte-for-byte unchanged behavior ---


def test_no_high_impact_event_context_matches_pre_existing_behavior_exactly() -> None:
    with_default_param = evaluate_decision_risk_pipeline(
        flow=None,
        technical=trend_following_technical(),
        external=None,
        context=_usd_context(),
        evaluation_time=NOW,
        symbol_facts=symbol_facts(),
        m15_market_structure=trend_following_market_structure(),
        account_risk_snapshot_assembly=ready_assembly(),
        trading_cycle_config=default_config(),
    )
    explicit_none = _run(high_impact_event_context=None)

    assert with_default_param.strategy_session_result == explicit_none.strategy_session_result
    assert with_default_param.high_impact_event_risk_result == explicit_none.high_impact_event_risk_result

    risk_result = with_default_param.strategy_session_result.strategy_portfolio_result.strategy_risk_result
    trend_risk = next(r for r in risk_result.family_results if r.family is StrategyFamily.TREND_FOLLOWING)
    assert trend_risk.verdict is RiskFamilyVerdict.ELIGIBLE_FOR_PORTFOLIO_REVIEW
