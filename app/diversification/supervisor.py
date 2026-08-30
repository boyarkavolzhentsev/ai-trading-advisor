"""Deterministic Portfolio/Diversification Supervisor (Stage 8).

Applies deterministic portfolio-risk policy over one already-produced
``StrategyRiskResult``: whether each family Risk produced a result for is
structurally and portfolio-risk-wise allowed to proceed to Stage 9 session
review, jointly against every other simultaneously Risk-eligible family
sharing that evaluation's single symbol. Never invokes Router/Judge/Policy/
Risk, never touches any analyst or supervisor package, never performs I/O -
a pure, synchronous, stateless function of its one input (see
``app.diversification.protocols.PortfolioSupervisorProtocol``).

Reads only ``RiskFamilyVerdict``, each family's ``max_individual_risk``, and
the account facts already embedded on ``strategy_risk_result.account_snapshot``/
``strategy_risk_result.trading_cycle_config`` - never a Judge ``direction``,
never a Flow/Technical/External Intelligence observation. Whether a family's
portfolio-risk allocation fits the account's shared capacity is exactly the
information this gate is allowed to act on; what any evidence means, or
which direction a family favors, is Stage 6B/6C's question, answered
upstream, never re-asked here.

Every simultaneously Risk-eligible family is scaled by the *identical*
proportional factor against the *same* shared capacity: no budget is
reserved, sequenced, or preferentially assigned between family results, and
no family is ever favored over another. Opposite-direction, same-symbol
families are never netted or offset - Stage 8 never reads direction at all.
"""

from __future__ import annotations

from decimal import Decimal

from app.core.enums.portfolio import PortfolioBlockReason, PortfolioFamilyVerdict, PortfolioGateOutcome
from app.core.enums.risk_gate import RiskFamilyVerdict
from app.core.models.portfolio_result import PortfolioFamilyResult, StrategyPortfolioResult
from app.core.models.risk_gate_result import AccountRiskSnapshot, RiskFamilyResult, StrategyRiskResult
from app.core.config.trading_cycle import TradingCycleConfig


def _remaining_portfolio_capacity(account_snapshot: AccountRiskSnapshot, trading_cycle_config: TradingCycleConfig) -> Decimal:
    """A locally-owned copy of the portfolio-capacity arithmetic - not
    imported from ``app.core.models.portfolio_result`` (whose own model
    validator independently re-derives the identical figure to self-validate
    its own fields), mirroring the Stage 5A/6A/6C/7 precedent of the
    operational component and the result model's self-validation
    maintaining independent copies of the same primitive rather than
    cross-importing one from the other."""
    portfolio_risk_budget = account_snapshot.current_equity * (trading_cycle_config.portfolio_risk_limit_percent / Decimal("100"))
    return max(Decimal("0"), portfolio_risk_budget - account_snapshot.current_open_risk_to_stop)


def _evaluate_family(
    risk_result: RiskFamilyResult,
    remaining_portfolio_capacity: Decimal,
    total_requested: Decimal,
) -> PortfolioFamilyResult:
    if risk_result.verdict is RiskFamilyVerdict.BLOCKED_BY_RISK:
        return PortfolioFamilyResult(
            family=risk_result.family,
            verdict=PortfolioFamilyVerdict.BLOCKED_BY_PORTFOLIO,
            reasons=(PortfolioBlockReason.RISK_NOT_ELIGIBLE,),
        )

    if remaining_portfolio_capacity <= 0:
        return PortfolioFamilyResult(
            family=risk_result.family,
            verdict=PortfolioFamilyVerdict.BLOCKED_BY_PORTFOLIO,
            reasons=(PortfolioBlockReason.GLOBAL_PORTFOLIO_CAP_REACHED,),
        )

    assert risk_result.max_individual_risk is not None  # guaranteed by RiskFamilyResult's own invariants

    if total_requested <= remaining_portfolio_capacity:
        portfolio_allocated_risk = risk_result.max_individual_risk
    else:
        scaling_factor = remaining_portfolio_capacity / total_requested
        portfolio_allocated_risk = risk_result.max_individual_risk * scaling_factor

    return PortfolioFamilyResult(
        family=risk_result.family,
        verdict=PortfolioFamilyVerdict.ELIGIBLE_FOR_SESSION_REVIEW,
        portfolio_allocated_risk=portfolio_allocated_risk,
    )


class PortfolioSupervisor:
    """Deterministic Stage 8 aggregator over one ``StrategyRiskResult``."""

    def evaluate(self, *, strategy_risk_result: StrategyRiskResult) -> StrategyPortfolioResult:
        remaining_portfolio_capacity = _remaining_portfolio_capacity(
            strategy_risk_result.account_snapshot, strategy_risk_result.trading_cycle_config
        )
        eligible_results = [
            result for result in strategy_risk_result.family_results if result.verdict is RiskFamilyVerdict.ELIGIBLE_FOR_PORTFOLIO_REVIEW
        ]
        total_requested = sum((result.max_individual_risk for result in eligible_results), Decimal("0"))

        family_results = tuple(
            _evaluate_family(risk_result, remaining_portfolio_capacity, total_requested)
            for risk_result in strategy_risk_result.family_results
        )
        any_eligible = any(result.verdict is PortfolioFamilyVerdict.ELIGIBLE_FOR_SESSION_REVIEW for result in family_results)
        outcome = (
            PortfolioGateOutcome.SOME_ELIGIBLE_FOR_SESSION_REVIEW if any_eligible else PortfolioGateOutcome.NO_PORTFOLIO_ELIGIBLE_FAMILY
        )

        return StrategyPortfolioResult(
            strategy_risk_result=strategy_risk_result,
            outcome=outcome,
            family_results=family_results,
        )


__all__ = ["PortfolioSupervisor"]
