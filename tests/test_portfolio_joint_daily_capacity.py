"""Stage 8 corrective coverage: joint Stage 7 daily-loss / Stage 8 portfolio
risk-capacity enforcement.

Prior to this correction, Stage 8 scaled every simultaneously Risk-eligible
family's allocation against only its own ``portfolio_risk_limit_percent``-
derived capacity, never against Stage 7's shared, daily-loss-derived
``available_new_trade_risk`` - so the sum of every family's
``portfolio_allocated_risk`` could exceed Stage 7's shared daily-loss
capacity even though every individual Stage 7 family verdict, and Stage 8's
own portfolio cap, were each independently valid (see the approved Stage
7->8 corrective-design audit). ``PortfolioSupervisor`` now derives
``joint_new_risk_capacity = min(stage7_shared_capacity,
stage8_portfolio_capacity)`` and scales against it instead.

V1 architectural note: ``MEAN_REVERSION`` has no approved Stage 6B semantic
mapping and is always Judge-``INSUFFICIENT_EVIDENCE`` (pinned by
``tests/test_judge_mean_reversion.py``), so at most 3 of the 4
``StrategyFamily`` members can ever be simultaneously Risk-eligible through
the real Router/Judge/Policy/Risk chain in V1. The corrective design audit's
worked example used 4 synthetic families (500 each, total requested 2000,
shared capacity 1500, scaling factor 0.75, 375 each) purely to illustrate
the arithmetic; ``test_critical_regression_daily_capacity_binds_below_
portfolio_capacity`` below reproduces the identical, most safety-critical
numbers from that example - scaling_factor == 0.75 and per-family allocation
== 375 - with the real 3-family V1 maximum, by using existing open risk to
bring Stage 7's shared capacity down to 1125 (0.75 x the 1500 total
requested by 3 x 500 ceilings), while Stage 8's own portfolio capacity stays
ample and therefore never the binding constraint. This is the load-bearing
regression test for the fix.
"""

from __future__ import annotations

from decimal import Decimal

from app.core.enums.portfolio import PortfolioBlockReason, PortfolioFamilyVerdict
from app.core.enums.session import TradingSessionStatus
from app.core.enums.session_gate import SessionFamilyVerdict
from app.core.enums.strategy_router import StrategyFamily
from app.core.models.portfolio_result import StrategyPortfolioResult
from app.diversification.supervisor import PortfolioSupervisor
from app.statistics.session import SessionGate
from tests.market_evaluation_support import full_flow_result, full_technical_result, make_context
from tests.portfolio_support import route_judge_gate_risk_and_portfolio, technical_with_trend_and_confirmed_break
from tests.risk_gate_support import default_account_snapshot, default_config
from tests.strategy_judge_support import external_with_news_sentiment

_THREE_FAMILY_TECHNICAL = technical_with_trend_and_confirmed_break()


def _three_family_portfolio_result(
    *,
    rollover_equity: Decimal,
    current_equity: Decimal,
    current_open_risk_to_stop: Decimal = Decimal("0"),
    realized_daily_pnl: Decimal = Decimal("0"),
    floating_pnl: Decimal = Decimal("0"),
    **config_overrides: object,
) -> StrategyPortfolioResult:
    """3 simultaneously Risk-eligible families: TREND_FOLLOWING, BREAKOUT,
    EVENT_DRIVEN (MEAN_REVERSION always Policy-blocked in V1 - see module
    docstring)."""
    snapshot = default_account_snapshot(
        rollover_equity=rollover_equity,
        current_equity=current_equity,
        current_open_risk_to_stop=current_open_risk_to_stop,
        realized_daily_pnl=realized_daily_pnl,
        floating_pnl=floating_pnl,
    )
    config = default_config(**config_overrides) if config_overrides else None
    _, portfolio_result = route_judge_gate_risk_and_portfolio(
        technical=_THREE_FAMILY_TECHNICAL,
        flow=full_flow_result(),
        external=external_with_news_sentiment(provider_signs={"p1": "POSITIVE", "p2": "POSITIVE"}),
        context=make_context(),
        account_snapshot=snapshot,
        trading_cycle_config=config,
        risk_per_unit=Decimal("10"),
    )
    return portfolio_result


def _eligible(portfolio_result: StrategyPortfolioResult):
    return [r for r in portfolio_result.family_results if r.verdict is PortfolioFamilyVerdict.ELIGIBLE_FOR_SESSION_REVIEW]


def _blocked(portfolio_result: StrategyPortfolioResult):
    return [r for r in portfolio_result.family_results if r.verdict is PortfolioFamilyVerdict.BLOCKED_BY_PORTFOLIO]


def _blocked_with_reason(portfolio_result: StrategyPortfolioResult, reason: PortfolioBlockReason):
    """MEAN_REVERSION is always ``RISK_NOT_ELIGIBLE`` in V1 (Policy-blocked
    upstream - see module docstring), so it is excluded here: only the 3
    real Risk-eligible-turned-portfolio-blocked families are relevant to
    the capacity-exhaustion reason under test."""
    return [r for r in portfolio_result.family_results if r.verdict is PortfolioFamilyVerdict.BLOCKED_BY_PORTFOLIO and r.reasons == (reason,)]


# --- 1. one eligible family ---


def test_one_eligible_family_ample_both_capacities_unscaled() -> None:
    _, portfolio_result = route_judge_gate_risk_and_portfolio(technical=full_technical_result())
    trend = next(r for r in portfolio_result.family_results if r.family is StrategyFamily.TREND_FOLLOWING)
    assert trend.verdict is PortfolioFamilyVerdict.ELIGIBLE_FOR_SESSION_REVIEW
    assert trend.portfolio_allocated_risk == Decimal("500.000")


# --- 2. multiple families below both capacities ---


def test_multiple_families_below_both_capacities_unscaled() -> None:
    # per-family ceiling 500 (rollover=100000, per-trade 0.5%); stage7 = 1500 (daily 1.5%);
    # stage8 = 100000 * 6% = 6000 (current_equity default 100000). total_requested = 1500 <= min(1500, 6000).
    portfolio_result = _three_family_portfolio_result(rollover_equity=Decimal("100000"), current_equity=Decimal("100000"))
    eligible = _eligible(portfolio_result)
    assert len(eligible) == 3
    for result in eligible:
        assert result.portfolio_allocated_risk == Decimal("500.000")


# --- 3. daily capacity tighter than portfolio capacity (and 12. via open risk) ---


def test_daily_capacity_tighter_than_portfolio_capacity_scales() -> None:
    # stage7 = 100000 * 1.5% - open_risk(600) = 900; stage8 = 10,000,000 * 6% = 600,000 (ample).
    # total_requested = 1500 > 900 -> scale = 900/1500 = 0.6 -> 300 each.
    portfolio_result = _three_family_portfolio_result(
        rollover_equity=Decimal("100000"), current_equity=Decimal("10000000"), current_open_risk_to_stop=Decimal("600")
    )
    eligible = _eligible(portfolio_result)
    assert len(eligible) == 3
    for result in eligible:
        assert result.portfolio_allocated_risk == Decimal("300.0")
    total = sum((r.portfolio_allocated_risk for r in eligible), Decimal("0"))
    assert total == Decimal("900.0")
    assert total <= Decimal("900")  # stage7_shared_capacity
    assert total <= Decimal("600000")  # stage8_portfolio_capacity


def test_critical_regression_daily_capacity_binds_below_portfolio_capacity() -> None:
    """Load-bearing regression for the corrective fix.

    Reproduces the design audit's worked example numbers exactly:
    per-family Stage 7 ceiling 500, scaling_factor 0.75, allocation-per-
    family 375 - via the real V1 maximum of 3 simultaneously Risk-eligible
    families (500 x 3 = 1500 total requested) against a Stage 7 shared
    capacity deliberately reduced to 1125 (= 0.75 x 1500) by existing open
    risk, while Stage 8's own portfolio capacity is kept ample and is never
    the binding constraint - proving Stage 8 now enforces Stage 7's shared
    daily-loss capacity, not just its own portfolio-percent capacity.

    Before this fix, PortfolioSupervisor ignored stage7_shared_capacity
    entirely and would have allocated the full 500 to every family (1500
    aggregate) here, exceeding the account's 1125 remaining daily-loss
    capacity by 375 while reporting every family ELIGIBLE_FOR_SESSION_REVIEW.
    """
    portfolio_result = _three_family_portfolio_result(
        rollover_equity=Decimal("100000"), current_equity=Decimal("100000000"), current_open_risk_to_stop=Decimal("375")
    )
    eligible = _eligible(portfolio_result)
    assert len(eligible) == 3
    assert {r.family for r in eligible} == {StrategyFamily.TREND_FOLLOWING, StrategyFamily.BREAKOUT, StrategyFamily.EVENT_DRIVEN}
    for result in eligible:
        assert result.portfolio_allocated_risk == Decimal("375.0")
    total = sum((r.portfolio_allocated_risk for r in eligible), Decimal("0"))
    assert total == Decimal("1125.0")
    assert total <= Decimal("1125")  # stage7_shared_capacity: 100000 * 1.5% - 375 = 1125
    assert total <= Decimal("6000000")  # stage8_portfolio_capacity: 100000000 * 6% = 6,000,000, never binding


# --- 4. portfolio capacity tighter than daily capacity ---


def test_portfolio_capacity_tighter_than_daily_capacity_scales() -> None:
    # stage7 = 1,000,000 * 1.5% = 15000 (ample); stage8 = 100000 * 6% = 6000.
    # total_requested = 15000 (3 x 5000, per-trade 0.5% of 1,000,000) > 6000 -> scale = 0.4 -> 2000 each.
    portfolio_result = _three_family_portfolio_result(rollover_equity=Decimal("1000000"), current_equity=Decimal("100000"))
    eligible = _eligible(portfolio_result)
    assert len(eligible) == 3
    for result in eligible:
        assert result.portfolio_allocated_risk == Decimal("2000.0")
    total = sum((r.portfolio_allocated_risk for r in eligible), Decimal("0"))
    assert total == Decimal("6000.0")


# --- 5. equal capacities ---


def test_equal_stage7_and_stage8_capacities_scale_identically() -> None:
    # rollover=current_equity=100000, daily=portfolio=1.5%, open_risk=600 -> both capacities = 900.
    # per-trade 0.5% -> ceiling 500 each; total_requested 1500 > 900 -> scale = 0.6 -> 300 each.
    portfolio_result = _three_family_portfolio_result(
        rollover_equity=Decimal("100000"),
        current_equity=Decimal("100000"),
        current_open_risk_to_stop=Decimal("600"),
        daily_risk_limit_percent=Decimal("1.5"),
        portfolio_risk_limit_percent=Decimal("1.5"),
        per_trade_risk_limit_percent=Decimal("0.5"),
    )
    eligible = _eligible(portfolio_result)
    assert len(eligible) == 3
    for result in eligible:
        assert result.portfolio_allocated_risk == Decimal("300.0")
    total = sum((r.portfolio_allocated_risk for r in eligible), Decimal("0"))
    assert total == Decimal("900.0")


# --- 6. total_requested exactly equals joint capacity (boundary, unscaled) ---


def test_total_requested_exactly_at_joint_capacity_boundary_unscaled() -> None:
    # stage7 = 100000 * 1.5% = 1500 == total_requested (3 x 500); stage8 ample -> no scaling at the boundary.
    portfolio_result = _three_family_portfolio_result(rollover_equity=Decimal("100000"), current_equity=Decimal("100000000"))
    eligible = _eligible(portfolio_result)
    assert len(eligible) == 3
    for result in eligible:
        assert result.portfolio_allocated_risk == Decimal("500.000")
    total = sum((r.portfolio_allocated_risk for r in eligible), Decimal("0"))
    assert total == Decimal("1500.000")


# --- 7. total_requested above the boundary (see critical regression + #4 above) ---


def test_total_requested_one_unit_above_joint_capacity_scales() -> None:
    # stage7 = 1500 - 1 = 1499 (open_risk=1) < total_requested 1500 -> scaling applies, however slight.
    portfolio_result = _three_family_portfolio_result(
        rollover_equity=Decimal("100000"), current_equity=Decimal("100000000"), current_open_risk_to_stop=Decimal("1")
    )
    eligible = _eligible(portfolio_result)
    assert len(eligible) == 3
    expected_each = Decimal("500.000") * (Decimal("1499") / Decimal("1500"))
    for result in eligible:
        assert result.portfolio_allocated_risk == expected_each
    total = sum((r.portfolio_allocated_risk for r in eligible), Decimal("0"))
    assert total <= Decimal("1499")


# --- 8. daily capacity = 0 ---


def test_daily_capacity_zero_is_already_blocked_upstream_at_stage7() -> None:
    """When Stage 7's shared daily capacity is fully exhausted, Stage 7
    itself already blocks every family with ``INSUFFICIENT_REMAINING_RISK_
    BUDGET`` before any family can ever reach Stage 8 as
    ``RiskFamilyVerdict.ELIGIBLE_FOR_PORTFOLIO_REVIEW`` - so Stage 8 sees
    only already-blocked families and reports ``RISK_NOT_ELIGIBLE``, never
    reaching its own capacity check. ``stage7_shared_capacity <= 0`` can
    therefore never be observed at Stage 8 for a real, self-consistent
    ``StrategyRiskResult`` - ``StrategyRiskResult``'s own self-validation
    would reject any hand-built object claiming otherwise, since it
    independently re-derives and enforces this exact Stage 7 threshold.
    See ``test_daily_capacity_zero_evaluate_family_unit`` below for direct
    coverage of the ``DAILY_RISK_CAPACITY_EXHAUSTED`` branch itself, kept as
    defensive/future-proofing logic per the approved design."""
    portfolio_result = _three_family_portfolio_result(
        rollover_equity=Decimal("100000"), current_equity=Decimal("100000000"), current_open_risk_to_stop=Decimal("1500")
    )
    real_families = {StrategyFamily.TREND_FOLLOWING, StrategyFamily.BREAKOUT, StrategyFamily.EVENT_DRIVEN}
    blocked_risk_not_eligible = _blocked_with_reason(portfolio_result, PortfolioBlockReason.RISK_NOT_ELIGIBLE)
    assert {r.family for r in blocked_risk_not_eligible} >= real_families
    assert _blocked_with_reason(portfolio_result, PortfolioBlockReason.DAILY_RISK_CAPACITY_EXHAUSTED) == []
    assert _eligible(portfolio_result) == []


def test_daily_capacity_zero_evaluate_family_unit() -> None:
    """Direct white-box coverage of the ``DAILY_RISK_CAPACITY_EXHAUSTED``
    branch in ``PortfolioSupervisor._evaluate_family``, since it is
    unreachable through the real chain (see the test above): a synthetic,
    independently-valid ``RiskFamilyResult`` already marked
    ``ELIGIBLE_FOR_PORTFOLIO_REVIEW`` is fed directly to the pure function
    with ``stage7_shared_capacity=0``."""
    from app.core.enums.risk_gate import RiskFamilyVerdict
    from app.core.models.risk_gate_result import RiskFamilyResult
    from app.diversification.supervisor import _evaluate_family

    risk_result = RiskFamilyResult(
        family=StrategyFamily.TREND_FOLLOWING,
        verdict=RiskFamilyVerdict.ELIGIBLE_FOR_PORTFOLIO_REVIEW,
        max_individual_risk=Decimal("500"),
        recommended_units=Decimal("50"),
    )
    result = _evaluate_family(
        risk_result,
        stage7_shared_capacity=Decimal("0"),
        stage8_portfolio_capacity=Decimal("6000"),
        joint_new_risk_capacity=Decimal("0"),
        total_requested=Decimal("1500"),
    )
    assert result.verdict is PortfolioFamilyVerdict.BLOCKED_BY_PORTFOLIO
    assert result.reasons == (PortfolioBlockReason.DAILY_RISK_CAPACITY_EXHAUSTED,)
    assert result.portfolio_allocated_risk is None


# --- 9. portfolio capacity = 0 ---


def test_portfolio_capacity_zero_blocks_with_portfolio_reason() -> None:
    # stage7 ample (rollover=1,000,000 -> 15000); open_risk (6000) exactly consumes stage8's 6000 (current_equity=100000, 6%).
    portfolio_result = _three_family_portfolio_result(
        rollover_equity=Decimal("1000000"), current_equity=Decimal("100000"), current_open_risk_to_stop=Decimal("6000")
    )
    blocked = _blocked_with_reason(portfolio_result, PortfolioBlockReason.GLOBAL_PORTFOLIO_CAP_REACHED)
    assert len(blocked) == 3
    for result in blocked:
        assert result.portfolio_allocated_risk is None


# --- 10. both capacities = 0 (daily takes precedence) ---


def test_both_capacities_zero_real_chain_already_blocked_at_stage7() -> None:
    """As with #8: stage7_shared_capacity == 0 is caught by Stage 7 itself
    before Stage 8 ever runs, regardless of stage8_portfolio_capacity's own
    value - confirming the "both zero" precedence question is moot for any
    real, self-consistent ``StrategyRiskResult``."""
    portfolio_result = _three_family_portfolio_result(
        rollover_equity=Decimal("100000"),
        current_equity=Decimal("100000"),
        current_open_risk_to_stop=Decimal("1500"),
        daily_risk_limit_percent=Decimal("1.5"),
        portfolio_risk_limit_percent=Decimal("1.5"),
    )
    assert _eligible(portfolio_result) == []
    assert _blocked_with_reason(portfolio_result, PortfolioBlockReason.DAILY_RISK_CAPACITY_EXHAUSTED) == []
    assert _blocked_with_reason(portfolio_result, PortfolioBlockReason.GLOBAL_PORTFOLIO_CAP_REACHED) == []


def test_both_capacities_zero_daily_reason_takes_precedence_unit() -> None:
    """Direct white-box coverage of the both-zero precedence rule in
    ``PortfolioSupervisor._evaluate_family``: ``DAILY_RISK_CAPACITY_
    EXHAUSTED`` wins over ``GLOBAL_PORTFOLIO_CAP_REACHED`` whenever both
    shared capacities are simultaneously non-positive."""
    from app.core.enums.risk_gate import RiskFamilyVerdict
    from app.core.models.risk_gate_result import RiskFamilyResult
    from app.diversification.supervisor import _evaluate_family

    risk_result = RiskFamilyResult(
        family=StrategyFamily.TREND_FOLLOWING,
        verdict=RiskFamilyVerdict.ELIGIBLE_FOR_PORTFOLIO_REVIEW,
        max_individual_risk=Decimal("500"),
        recommended_units=Decimal("50"),
    )
    result = _evaluate_family(
        risk_result,
        stage7_shared_capacity=Decimal("0"),
        stage8_portfolio_capacity=Decimal("0"),
        joint_new_risk_capacity=Decimal("0"),
        total_requested=Decimal("1500"),
    )
    assert result.reasons == (PortfolioBlockReason.DAILY_RISK_CAPACITY_EXHAUSTED,)


# --- 11. tiny positive Decimal capacity ---


def test_tiny_positive_daily_capacity_still_eligible_and_scaled() -> None:
    # stage7 = 1500 - 1499.99 = 0.01 (tiny, positive); stage8 ample -> eligible, scaled to a tiny positive sum.
    from app.diversification.supervisor import _remaining_portfolio_capacity, _stage7_shared_capacity

    snapshot = default_account_snapshot(
        rollover_equity=Decimal("100000"), current_equity=Decimal("100000000"), current_open_risk_to_stop=Decimal("1499.99")
    )
    config = default_config()
    risk_result, portfolio_result = route_judge_gate_risk_and_portfolio(
        technical=_THREE_FAMILY_TECHNICAL,
        flow=full_flow_result(),
        external=external_with_news_sentiment(provider_signs={"p1": "POSITIVE", "p2": "POSITIVE"}),
        context=make_context(),
        account_snapshot=snapshot,
        risk_per_unit=Decimal("10"),
    )
    eligible = _eligible(portfolio_result)
    daily_blocked = _blocked_with_reason(portfolio_result, PortfolioBlockReason.DAILY_RISK_CAPACITY_EXHAUSTED)
    portfolio_blocked = _blocked_with_reason(portfolio_result, PortfolioBlockReason.GLOBAL_PORTFOLIO_CAP_REACHED)
    assert len(eligible) == 3
    assert len(daily_blocked) == 0
    assert len(portfolio_blocked) == 0

    stage7_shared_capacity = _stage7_shared_capacity(snapshot, config)
    stage8_portfolio_capacity = _remaining_portfolio_capacity(snapshot, config)
    joint_new_risk_capacity = min(stage7_shared_capacity, stage8_portfolio_capacity)
    assert Decimal("0") < joint_new_risk_capacity < Decimal("1")
    eligible_ceilings = [r.max_individual_risk for r in risk_result.family_results if r.max_individual_risk is not None]
    total_requested = sum(eligible_ceilings, Decimal("0"))
    scaling_factor = joint_new_risk_capacity / total_requested

    for result, ceiling in zip(eligible, eligible_ceilings, strict=True):
        assert result.portfolio_allocated_risk > 0
        assert result.portfolio_allocated_risk == ceiling * scaling_factor
    total = sum((r.portfolio_allocated_risk for r in eligible), Decimal("0"))
    assert total <= joint_new_risk_capacity


# --- 13. existing open risk consuming portfolio capacity (stage7 ample, unaffected regime) ---


def test_existing_open_risk_consumes_portfolio_capacity_stage7_ample() -> None:
    # stage7 = 1,000,000 * 1.5% = 15000 (ample); stage8 = 100000*6% - 3000(open risk) = 3000.
    portfolio_result = _three_family_portfolio_result(
        rollover_equity=Decimal("1000000"), current_equity=Decimal("100000"), current_open_risk_to_stop=Decimal("3000")
    )
    eligible = _eligible(portfolio_result)
    assert len(eligible) == 3
    expected_each = Decimal("5000.000") * (Decimal("3000") / Decimal("15000"))
    for result in eligible:
        assert result.portfolio_allocated_risk == expected_each
    total = sum((r.portfolio_allocated_risk for r in eligible), Decimal("0"))
    assert total == Decimal("3000.000")


# --- 14. positive daily PnL does not increase the daily loss limit ---


def test_positive_daily_pnl_does_not_increase_daily_capacity() -> None:
    zero_pnl = _three_family_portfolio_result(
        rollover_equity=Decimal("100000"), current_equity=Decimal("100000000"), current_open_risk_to_stop=Decimal("375")
    )
    positive_pnl = _three_family_portfolio_result(
        rollover_equity=Decimal("100000"),
        current_equity=Decimal("100000000"),
        current_open_risk_to_stop=Decimal("375"),
        realized_daily_pnl=Decimal("0"),
        floating_pnl=Decimal("0"),
    )
    # Re-derive with genuinely positive PnL: loss_consumed floors at 0, so daily_loss_limit (1500) is unaffected,
    # and stage7_shared_capacity stays 1500 - 375 = 1125 either way.
    positive_pnl_2 = _three_family_portfolio_result(
        rollover_equity=Decimal("100000"),
        current_equity=Decimal("100000000"),
        current_open_risk_to_stop=Decimal("375"),
        realized_daily_pnl=Decimal("5000"),
        floating_pnl=Decimal("2000"),
    )
    zero_eligible = _eligible(zero_pnl)
    positive_eligible = _eligible(positive_pnl)
    positive_eligible_2 = _eligible(positive_pnl_2)
    for a, b, c in zip(zero_eligible, positive_eligible, positive_eligible_2, strict=True):
        assert a.portfolio_allocated_risk == b.portfolio_allocated_risk == c.portfolio_allocated_risk == Decimal("375.0")


# --- 15. proportional allocation is order-independent across canonical family positions ---


def test_scaling_factor_identical_regardless_of_family_canonical_position() -> None:
    """TREND_FOLLOWING (1st canonical position), BREAKOUT (3rd) and
    EVENT_DRIVEN (4th) all receive the identical scaling factor - no
    positional/order bias in which family appears first."""
    portfolio_result = _three_family_portfolio_result(
        rollover_equity=Decimal("100000"), current_equity=Decimal("100000000"), current_open_risk_to_stop=Decimal("375")
    )
    by_family = {r.family: r for r in portfolio_result.family_results if r.verdict is PortfolioFamilyVerdict.ELIGIBLE_FOR_SESSION_REVIEW}
    assert (
        by_family[StrategyFamily.TREND_FOLLOWING].portfolio_allocated_risk
        == by_family[StrategyFamily.BREAKOUT].portfolio_allocated_risk
        == by_family[StrategyFamily.EVENT_DRIVEN].portfolio_allocated_risk
        == Decimal("375.0")
    )


def test_total_requested_sum_is_order_independent_decimal_arithmetic() -> None:
    ceilings = [Decimal("500"), Decimal("500"), Decimal("500")]
    forward = sum(ceilings, Decimal("0"))
    backward = sum(reversed(ceilings), Decimal("0"))
    shuffled = ceilings[1] + ceilings[2] + ceilings[0]
    assert forward == backward == shuffled == Decimal("1500")


# --- 16. exact Decimal determinism ---


def test_repeated_evaluation_is_bit_identical() -> None:
    first = _three_family_portfolio_result(
        rollover_equity=Decimal("100000"), current_equity=Decimal("100000000"), current_open_risk_to_stop=Decimal("375")
    )
    second = _three_family_portfolio_result(
        rollover_equity=Decimal("100000"), current_equity=Decimal("100000000"), current_open_risk_to_stop=Decimal("375")
    )
    for a, b in zip(first.family_results, second.family_results, strict=True):
        assert a.portfolio_allocated_risk == b.portfolio_allocated_risk
        assert type(a.portfolio_allocated_risk) in (type(None), Decimal)
        if a.portfolio_allocated_risk is not None:
            assert str(a.portfolio_allocated_risk) == str(b.portfolio_allocated_risk)


def test_direct_supervisor_call_reproduces_identical_result() -> None:
    """Calling PortfolioSupervisor().evaluate() directly on the same
    StrategyRiskResult twice is a pure function - identical output both
    times."""
    risk_result, _ = route_judge_gate_risk_and_portfolio(
        technical=_THREE_FAMILY_TECHNICAL,
        flow=full_flow_result(),
        external=external_with_news_sentiment(provider_signs={"p1": "POSITIVE", "p2": "POSITIVE"}),
        context=make_context(),
        account_snapshot=default_account_snapshot(
            rollover_equity=Decimal("100000"), current_equity=Decimal("100000000"), current_open_risk_to_stop=Decimal("375")
        ),
        risk_per_unit=Decimal("10"),
    )
    first = PortfolioSupervisor().evaluate(strategy_risk_result=risk_result)
    second = PortfolioSupervisor().evaluate(strategy_risk_result=risk_result)
    assert first == second


# --- 17. Stage 9 passes corrected allocations through unchanged when ACTIVE ---


def test_stage9_active_pass_through_matches_corrected_stage8_allocation() -> None:
    # current_equity == rollover_equity (session pnl 0, TARGET_REACHED never triggers); stage8 budget
    # 100000 * 6% - 375 = 5625, still ample relative to the 1125 stage7 capacity below.
    snapshot = default_account_snapshot(
        rollover_equity=Decimal("100000"), current_equity=Decimal("100000"), current_open_risk_to_stop=Decimal("375")
    )
    _, portfolio_result = route_judge_gate_risk_and_portfolio(
        technical=_THREE_FAMILY_TECHNICAL,
        flow=full_flow_result(),
        external=external_with_news_sentiment(provider_signs={"p1": "POSITIVE", "p2": "POSITIVE"}),
        context=make_context(),
        account_snapshot=snapshot,
        risk_per_unit=Decimal("10"),
    )
    session_result = SessionGate().evaluate(strategy_portfolio_result=portfolio_result, locked_override=False)

    assert session_result.session_status is TradingSessionStatus.ACTIVE
    eligible_portfolio = {r.family: r for r in portfolio_result.family_results if r.verdict is PortfolioFamilyVerdict.ELIGIBLE_FOR_SESSION_REVIEW}
    eligible_session = {
        r.family: r for r in session_result.family_results if r.verdict is SessionFamilyVerdict.ELIGIBLE_FOR_RUNTIME_REVIEW
    }
    assert set(eligible_portfolio) == set(eligible_session) == {
        StrategyFamily.TREND_FOLLOWING,
        StrategyFamily.BREAKOUT,
        StrategyFamily.EVENT_DRIVEN,
    }
    for family, portfolio_family_result in eligible_portfolio.items():
        assert eligible_session[family].session_allocated_risk == portfolio_family_result.portfolio_allocated_risk
        assert eligible_session[family].session_allocated_risk == Decimal("375.0")
