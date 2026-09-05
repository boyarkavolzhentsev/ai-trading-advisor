"""Shared builders for Decision/Risk Pipeline tests.

Builds real per-family Stage 5 inputs via the same upstream support modules
Setup Construction/Judge tests already use, plus a READY/BLOCKED
``AccountRiskSnapshotAssembly`` via the real ``assemble_account_risk_snapshot``
- never a hand-rolled pipeline result. Not a test module itself (no ``test_``
prefix): pytest will not collect it.
"""

from __future__ import annotations

from decimal import Decimal

from app.core.enums.mt5_rollover import MT5RolloverOutcome
from app.core.enums.technical import BreakDirection, SwingKind
from app.core.models.market_evaluation_context import MarketEvaluationContext
from app.core.models.market_structure_features import MarketStructureFeatures
from app.core.models.mt5_symbol import MT5SymbolFacts
from app.core.models.runtime_fact_assembly import AccountRiskSnapshotAssembly
from app.core.models.technical_supervisor_result import TechnicalSupervisorResult
from app.orchestration.facts import assemble_account_risk_snapshot
from tests.market_evaluation_support import NOW, make_context
from tests.runtime_fact_assembly_support import (
    AS_OF,
    rollover_ready,
    rollover_unusable,
    usable_open_risk,
    usable_realized_pnl,
)
from tests.setup_construction_support import structural_break, swing, symbol_facts as _symbol_facts, usable_market_structure
from tests.strategy_judge_support import technical_with_market_structure_break, technical_with_trend_observations

__all__ = [
    "NOW",
    "blocked_assembly",
    "combined_trend_and_breakout_technical",
    "combined_trend_and_breakout_market_structure",
    "context",
    "ready_assembly",
    "symbol_facts",
    "trend_following_market_structure",
    "trend_following_technical",
]


def context(**overrides: object) -> MarketEvaluationContext:
    return make_context(**overrides)


def symbol_facts(**overrides: object) -> MT5SymbolFacts:
    return _symbol_facts(**overrides)


def trend_following_technical(
    *, return_direction: str | None = "UPWARD", slope_direction: str | None = "UPWARD"
) -> TechnicalSupervisorResult:
    return technical_with_trend_observations(return_direction=return_direction, slope_direction=slope_direction)


def trend_following_market_structure() -> MarketStructureFeatures:
    """A usable M15 structure with one LOW swing - the support
    TREND_FOLLOWING's LONG stop rule requires (see
    ``app.decision.setup_construction._select_trend_following_stop``)."""
    return usable_market_structure(swings=(swing(kind=SwingKind.LOW, price=Decimal("90")),))


def combined_trend_and_breakout_technical() -> TechnicalSupervisorResult:
    """TREND_FOLLOWING (RETURN_DIRECTION/SLOPE_DIRECTION) and BREAKOUT
    (STRUCTURAL_BREAK_PRESENCE/LATEST_BREAK_DIRECTION) both directional LONG
    on the same technical contour - used to exercise two simultaneously
    Setup-``CONSTRUCTED``, Risk-eligible families."""
    return technical_with_market_structure_break(break_direction="UPWARD_BREAK", return_direction="UPWARD")


def combined_trend_and_breakout_market_structure() -> MarketStructureFeatures:
    low_swing = swing(kind=SwingKind.LOW, price=Decimal("90"))
    break_ = structural_break(broken_swing=low_swing, break_close=Decimal("101"), direction=BreakDirection.UPWARD_BREAK)
    return usable_market_structure(swings=(low_swing,), breaks=(break_,))


def ready_assembly(**overrides: object) -> AccountRiskSnapshotAssembly:
    fields: dict[str, object] = {
        "as_of": AS_OF,
        "rollover_snapshot": rollover_ready(),
        "realized_daily_pnl_assessment": usable_realized_pnl(),
        "open_risk_assessment": usable_open_risk(),
    }
    fields.update(overrides)
    return assemble_account_risk_snapshot(**fields)


def blocked_assembly(**overrides: object) -> AccountRiskSnapshotAssembly:
    fields: dict[str, object] = {
        "as_of": AS_OF,
        "rollover_snapshot": rollover_unusable(outcome=MT5RolloverOutcome.PERSISTENCE_UNAVAILABLE),
        "realized_daily_pnl_assessment": usable_realized_pnl(),
        "open_risk_assessment": usable_open_risk(),
    }
    fields.update(overrides)
    return assemble_account_risk_snapshot(**fields)
