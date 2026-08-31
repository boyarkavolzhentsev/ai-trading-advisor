"""Shared builders for Stage 9 session-gate tests.

Builds real ``StrategyPortfolioResult`` fixtures via the real
``StrategyRouter``/``Judge``/``PolicyGate``/``RiskGate``/``PortfolioSupervisor``
chain (reusing ``tests/portfolio_support.py`` and its own upstream support
modules), then runs them through the real ``SessionGate`` - never a
hand-rolled ``StrategySessionResult`` for anything but malformed-model
invariant tests. Not a test module itself (no ``test_`` prefix): pytest will
not collect it.
"""

from __future__ import annotations

from decimal import Decimal

from app.core.models.portfolio_result import StrategyPortfolioResult
from app.core.models.session_result import StrategySessionResult
from app.statistics.session import SessionGate
from tests.market_evaluation_support import full_flow_result, full_technical_result, make_context
from tests.portfolio_support import route_judge_gate_risk_and_portfolio, technical_with_trend_and_confirmed_break
from tests.risk_gate_support import default_account_snapshot
from tests.strategy_judge_support import external_with_news_sentiment

__all__ = [
    "route_to_portfolio_and_session",
    "single_family_portfolio_result",
    "three_family_portfolio_result",
]


def route_to_portfolio_and_session(
    *, locked_override: bool = False, **portfolio_kwargs: object
) -> tuple[StrategyPortfolioResult, StrategySessionResult]:
    """Defaults to a fixture with both a Portfolio-eligible family
    (TREND_FOLLOWING) and a Portfolio-blocked one (MEAN_REVERSION,
    structurally ineligible at Router) unless the caller overrides
    ``technical`` - so every boundary/precedence test exercises a realistic
    mixed family set, mirroring ``tests.portfolio_support``'s own default
    single-family fixture (``full_technical_result()``)."""
    portfolio_kwargs.setdefault("technical", full_technical_result())
    _, portfolio_result = route_judge_gate_risk_and_portfolio(**portfolio_kwargs)
    session_result = SessionGate().evaluate(strategy_portfolio_result=portfolio_result, locked_override=locked_override)
    return portfolio_result, session_result


def single_family_portfolio_result(**account_overrides: object) -> StrategyPortfolioResult:
    snapshot = default_account_snapshot(**account_overrides)
    _, portfolio_result = route_judge_gate_risk_and_portfolio(technical=full_technical_result(), account_snapshot=snapshot)
    return portfolio_result


def three_family_portfolio_result(**account_overrides: object) -> StrategyPortfolioResult:
    """Three simultaneously Portfolio-eligible families (TREND_FOLLOWING,
    BREAKOUT, EVENT_DRIVEN), mirroring
    ``tests.portfolio_support.technical_with_trend_and_confirmed_break``'s
    own multi-family fixture, with ample rollover equity so Stage 7 headroom
    never interferes with session-level boundary tests."""
    fields: dict[str, object] = {"rollover_equity": Decimal("1000000"), "current_open_risk_to_stop": Decimal("0")}
    fields.update(account_overrides)
    snapshot = default_account_snapshot(**fields)
    _, portfolio_result = route_judge_gate_risk_and_portfolio(
        technical=technical_with_trend_and_confirmed_break(),
        flow=full_flow_result(),
        external=external_with_news_sentiment(provider_signs={"p1": "POSITIVE", "p2": "POSITIVE"}),
        context=make_context(),
        account_snapshot=snapshot,
        risk_per_unit=Decimal("10"),
    )
    return portfolio_result
