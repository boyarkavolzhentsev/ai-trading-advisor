"""Deterministic Session Gate (Stage 9).

Applies deterministic session policy over one already-produced
``StrategyPortfolioResult``: whether each family Portfolio produced a result
for is allowed to proceed to Stage 10 runtime review under the account's
current, rollover-based session state. Never invokes Router/Judge/Policy/
Risk/Portfolio, never touches any analyst/supervisor package, never performs
I/O - a pure, synchronous, stateless function of its two explicit inputs
(see ``app.statistics.protocols.SessionGateProtocol``).

Reads only ``PortfolioFamilyVerdict``, each family's
``portfolio_allocated_risk``, the account facts already embedded on
``strategy_portfolio_result.strategy_risk_result.account_snapshot``/
``.trading_cycle_config``, and the caller-supplied ``locked_override`` -
never a Judge ``direction``, never a Flow/Technical/External Intelligence
observation. Whether the session is currently tradeable is exactly the
information this gate is allowed to act on; what any evidence means, what
direction a family favors, or how much risk it was allocated is Stage
6B/6C/7/8's question, answered upstream, never re-asked here.

Session status is a single global fact, computed once and applied
identically to every otherwise-eligible family - mirroring the "same shared
capacity for every family" discipline Stage 7/8 already enforce. Stage 7
remains the sole enforcement owner of the daily-loss rule; this gate only
re-derives its own locally-owned copy of that same formula to expose the
correct ``TradingSessionStatus`` for reporting - it never applies a second,
independent loss policy. Stage 9 V1 is a strict pass/block gate: an eligible
family's ``session_allocated_risk`` is always an exact, unscaled copy of its
upstream ``portfolio_allocated_risk`` - no risk-reduction formula is
implemented or approved for V1, so ``REDUCED_RISK``/``CAPITAL_PRESERVATION``
are never produced.
"""

from __future__ import annotations

from decimal import Decimal

from app.core.enums.portfolio import PortfolioFamilyVerdict
from app.core.enums.session import TradingSessionStatus
from app.core.enums.session_gate import SessionBlockReason, SessionFamilyVerdict, SessionGateOutcome
from app.core.models.portfolio_result import PortfolioFamilyResult, StrategyPortfolioResult
from app.core.models.session_result import SessionFamilyResult, StrategySessionResult

_SESSION_REASON_BY_STATUS: dict[TradingSessionStatus, SessionBlockReason] = {
    TradingSessionStatus.LOCKED: SessionBlockReason.SESSION_LOCKED,
    TradingSessionStatus.LOSS_LIMIT_REACHED: SessionBlockReason.LOSS_LIMIT_REACHED,
    TradingSessionStatus.TARGET_REACHED: SessionBlockReason.TARGET_REACHED,
}


def _derive_session_status(strategy_portfolio_result: StrategyPortfolioResult, locked_override: bool) -> TradingSessionStatus:
    """A locally-owned copy of the Stage 9 status precedence - not imported
    from ``app.core.models.session_result`` (whose own model validator
    independently re-derives the identical precedence to self-validate its
    own fields), mirroring the Stage 5A/6A/6C/7/8 precedent of the
    operational component and the result model's self-validation
    maintaining independent copies of the same primitive rather than
    cross-importing one from the other.

    Precedence, most conservative first: an explicit operator lock always
    wins; Stage 7's own daily-loss capacity exhaustion wins over a reached
    profit target; a reached target blocks further recommendations absent a
    stronger safety state; otherwise the session is active.
    """
    if locked_override:
        return TradingSessionStatus.LOCKED

    account_snapshot = strategy_portfolio_result.strategy_risk_result.account_snapshot
    trading_cycle_config = strategy_portfolio_result.strategy_risk_result.trading_cycle_config

    daily_loss_limit = account_snapshot.rollover_equity * (trading_cycle_config.daily_risk_limit_percent / Decimal("100"))
    current_daily_pnl = account_snapshot.realized_daily_pnl + account_snapshot.floating_pnl
    loss_consumed = max(Decimal("0"), -current_daily_pnl)
    remaining_daily_loss_capacity = max(Decimal("0"), daily_loss_limit - loss_consumed)
    if remaining_daily_loss_capacity <= 0:
        return TradingSessionStatus.LOSS_LIMIT_REACHED

    target_profit_amount = account_snapshot.rollover_equity * (trading_cycle_config.target_profit_percent / Decimal("100"))
    current_session_pnl = account_snapshot.current_equity - account_snapshot.rollover_equity
    if current_session_pnl >= target_profit_amount:
        return TradingSessionStatus.TARGET_REACHED

    return TradingSessionStatus.ACTIVE


def _evaluate_family(portfolio_result: PortfolioFamilyResult, session_status: TradingSessionStatus) -> SessionFamilyResult:
    if portfolio_result.verdict is PortfolioFamilyVerdict.BLOCKED_BY_PORTFOLIO:
        return SessionFamilyResult(
            family=portfolio_result.family,
            verdict=SessionFamilyVerdict.BLOCKED_BY_SESSION,
            reasons=(SessionBlockReason.PORTFOLIO_NOT_ELIGIBLE,),
        )

    if session_status is TradingSessionStatus.ACTIVE:
        return SessionFamilyResult(
            family=portfolio_result.family,
            verdict=SessionFamilyVerdict.ELIGIBLE_FOR_RUNTIME_REVIEW,
            session_allocated_risk=portfolio_result.portfolio_allocated_risk,
        )

    return SessionFamilyResult(
        family=portfolio_result.family,
        verdict=SessionFamilyVerdict.BLOCKED_BY_SESSION,
        reasons=(_SESSION_REASON_BY_STATUS[session_status],),
    )


class SessionGate:
    """Deterministic Stage 9 aggregator over one ``StrategyPortfolioResult``."""

    def evaluate(
        self, *, strategy_portfolio_result: StrategyPortfolioResult, locked_override: bool = False
    ) -> StrategySessionResult:
        session_status = _derive_session_status(strategy_portfolio_result, locked_override)

        family_results = tuple(
            _evaluate_family(portfolio_result, session_status)
            for portfolio_result in strategy_portfolio_result.family_results
        )
        any_eligible = any(result.verdict is SessionFamilyVerdict.ELIGIBLE_FOR_RUNTIME_REVIEW for result in family_results)
        outcome = (
            SessionGateOutcome.SOME_ELIGIBLE_FOR_RUNTIME_REVIEW if any_eligible else SessionGateOutcome.NO_SESSION_ELIGIBLE_FAMILY
        )

        return StrategySessionResult(
            strategy_portfolio_result=strategy_portfolio_result,
            locked_override=locked_override,
            session_status=session_status,
            outcome=outcome,
            family_results=family_results,
        )


__all__ = ["SessionGate"]
