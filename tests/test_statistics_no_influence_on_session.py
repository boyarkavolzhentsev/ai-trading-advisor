"""Stage 9: statistics must never influence session-gate eligibility.

``StatisticsAggregator`` and ``SessionGate`` are architecturally decoupled
(see ``tests/test_session_gate_no_coupling.py`` for the import-boundary
proof); this file proves the runtime behavior: an identical
``StrategyPortfolioResult``/``locked_override`` pair yields an identical
``StrategySessionResult`` no matter how the (entirely separate)
``PerformanceSnapshot`` for the same history varies.
"""

from __future__ import annotations

import inspect
from datetime import datetime
from decimal import Decimal

from app.core.config import SIGNAL_EXECUTION_WINDOW
from app.core.enums import MarketType, TradeDirection, TradeStatus
from app.core.models import PositionRecord
from app.statistics.aggregator import StatisticsAggregator
from app.statistics.session import SessionGate
from tests.session_support import route_to_portfolio_and_session


def _record(now: datetime, **overrides: object) -> PositionRecord:
    fields: dict[str, object] = {
        "trade_id": "T-1",
        "symbol": "TEST",
        "market": MarketType.FX,
        "direction": TradeDirection.LONG,
        "signal_time": now,
        "valid_until": now + SIGNAL_EXECUTION_WINDOW,
        "status": TradeStatus.WIN,
        "planned_entry": Decimal("100"),
        "stop_loss": Decimal("99"),
    }
    fields.update(overrides)
    return PositionRecord(**fields)


def test_session_gate_evaluate_has_no_statistics_parameter() -> None:
    signature = inspect.signature(SessionGate.evaluate)
    assert "records" not in signature.parameters
    assert "performance" not in signature.parameters
    assert "performance_snapshot" not in signature.parameters
    assert "statistics" not in signature.parameters


def test_wildly_different_statistics_do_not_change_session_result(now: datetime) -> None:
    portfolio_result, expected_session_result = route_to_portfolio_and_session()

    losing_history = tuple(_record(now, trade_id=f"L-{i}", status=TradeStatus.LOSS, pnl=Decimal("-1")) for i in range(50))
    winning_history = tuple(_record(now, trade_id=f"W-{i}", status=TradeStatus.WIN, pnl=Decimal("1")) for i in range(50))
    losing_snapshot = StatisticsAggregator().aggregate(records=losing_history)
    winning_snapshot = StatisticsAggregator().aggregate(records=winning_history)
    assert losing_snapshot.win_rate != winning_snapshot.win_rate

    session_result_after_losing_history = SessionGate().evaluate(strategy_portfolio_result=portfolio_result)
    session_result_after_winning_history = SessionGate().evaluate(strategy_portfolio_result=portfolio_result)

    assert session_result_after_losing_history == expected_session_result
    assert session_result_after_winning_history == expected_session_result
    assert session_result_after_losing_history == session_result_after_winning_history
