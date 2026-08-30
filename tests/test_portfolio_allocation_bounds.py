"""Stage 8 allocation bounds: ``portfolio_allocated_risk`` never exceeds its
Stage 7 ``max_individual_risk``, and the sum of allocations never exceeds
``remaining_portfolio_capacity`` - verified both on real-pipeline output and
via hand-constructed violations rejected at the model level."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.enums.portfolio import PortfolioFamilyVerdict, PortfolioGateOutcome
from app.core.models.portfolio_result import PortfolioFamilyResult, StrategyPortfolioResult
from tests.market_evaluation_support import full_flow_result, make_context
from tests.portfolio_support import route_judge_gate_risk_and_portfolio, technical_with_trend_and_confirmed_break
from tests.risk_gate_support import default_account_snapshot
from tests.strategy_judge_support import external_with_news_sentiment


def _scaled_portfolio_result():
    snapshot = default_account_snapshot(
        rollover_equity=Decimal("1000000"), current_equity=Decimal("100000"), current_open_risk_to_stop=Decimal("0")
    )
    _, portfolio_result = route_judge_gate_risk_and_portfolio(
        technical=technical_with_trend_and_confirmed_break(),
        flow=full_flow_result(),
        external=external_with_news_sentiment(provider_signs={"p1": "POSITIVE", "p2": "POSITIVE"}),
        context=make_context(),
        account_snapshot=snapshot,
        risk_per_unit=Decimal("10"),
    )
    return portfolio_result


def test_allocation_never_exceeds_max_individual_risk_on_real_output() -> None:
    portfolio_result = _scaled_portfolio_result()
    risk_by_family = {r.family: r for r in portfolio_result.strategy_risk_result.family_results}
    for result in portfolio_result.family_results:
        if result.portfolio_allocated_risk is None:
            continue
        assert result.portfolio_allocated_risk <= risk_by_family[result.family].max_individual_risk


def test_total_allocation_never_exceeds_remaining_capacity_on_real_output() -> None:
    portfolio_result = _scaled_portfolio_result()
    total = sum(
        (r.portfolio_allocated_risk for r in portfolio_result.family_results if r.portfolio_allocated_risk is not None),
        Decimal("0"),
    )
    # cap = 100,000 * 6% = 6000; open_risk = 0 -> remaining = 6000.
    assert total <= Decimal("6000")


def test_hand_constructed_allocation_exceeding_max_individual_risk_rejected() -> None:
    portfolio_result = _scaled_portfolio_result()
    tampered = tuple(
        PortfolioFamilyResult(
            family=r.family,
            verdict=r.verdict,
            reasons=r.reasons,
            portfolio_allocated_risk=(r.portfolio_allocated_risk + Decimal("1") if r.portfolio_allocated_risk is not None else None),
        )
        for r in portfolio_result.family_results
    )
    with pytest.raises(ValidationError):
        StrategyPortfolioResult(
            strategy_risk_result=portfolio_result.strategy_risk_result,
            outcome=portfolio_result.outcome,
            family_results=tampered,
        )


def test_hand_constructed_total_exceeding_remaining_capacity_rejected() -> None:
    """Even if each individual allocation stays within its own
    max_individual_risk, an inflated combination that busts the shared
    remaining capacity must still be rejected."""
    portfolio_result = _scaled_portfolio_result()
    eligible_families = [r.family for r in portfolio_result.family_results if r.verdict is PortfolioFamilyVerdict.ELIGIBLE_FOR_SESSION_REVIEW]
    assert len(eligible_families) >= 2
    risk_by_family = {r.family: r for r in portfolio_result.strategy_risk_result.family_results}

    inflated_results = []
    for r in portfolio_result.family_results:
        if r.family in eligible_families:
            # Set every eligible family's allocation to its full (unscaled) max_individual_risk -
            # individually valid, but jointly exceeds remaining_portfolio_capacity.
            inflated_results.append(
                PortfolioFamilyResult(
                    family=r.family,
                    verdict=PortfolioFamilyVerdict.ELIGIBLE_FOR_SESSION_REVIEW,
                    portfolio_allocated_risk=risk_by_family[r.family].max_individual_risk,
                )
            )
        else:
            inflated_results.append(r)

    with pytest.raises(ValidationError):
        StrategyPortfolioResult(
            strategy_risk_result=portfolio_result.strategy_risk_result,
            outcome=PortfolioGateOutcome.SOME_ELIGIBLE_FOR_SESSION_REVIEW,
            family_results=tuple(inflated_results),
        )
