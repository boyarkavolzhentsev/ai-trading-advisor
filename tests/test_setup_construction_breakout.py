"""Setup Construction BREAKOUT structural stop rule: the latest confirmed
M15 ``StructuralBreak`` (``breaks[-1]``), whose mapped direction must agree
with the already-authorized Judge thesis; ``stop_loss`` is the broken
swing's own price."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from app.core.enums.setup_construction import SetupBlockReason, SetupConstructionOutcome
from app.core.enums.strategy_router import StrategyFamily
from app.core.enums.technical import BreakDirection, SwingKind
from app.core.enums.trade import TradeDirection
from app.decision.setup_construction import SetupConstruction
from tests.setup_construction_support import AS_OF, breakout_policy_result, result_for, structural_break, swing, symbol_facts, usable_market_structure


def _construct(policy_result, *, market_structure, facts=None):
    return SetupConstruction().construct(
        strategy_policy_result=policy_result,
        as_of=AS_OF,
        symbol_facts=facts if facts is not None else symbol_facts(),
        m15_market_structure=market_structure,
    )


def test_upward_break_gives_long_setup() -> None:
    policy = breakout_policy_result(break_direction="UPWARD_BREAK")
    broken = swing(kind=SwingKind.HIGH, price=Decimal("100"))
    br = structural_break(broken_swing=broken, break_close=Decimal("105"), direction=BreakDirection.UPWARD_BREAK)
    ms = usable_market_structure(breaks=(br,))
    facts = symbol_facts(ask=Decimal("110"), bid=Decimal("109.5"))

    result = result_for(_construct(policy, market_structure=ms, facts=facts), StrategyFamily.BREAKOUT)

    assert result.outcome is SetupConstructionOutcome.CONSTRUCTED
    assert result.setup.direction is TradeDirection.LONG
    assert result.setup.entry_price == Decimal("110")
    assert result.setup.stop_loss == Decimal("100")


def test_downward_break_gives_short_setup() -> None:
    policy = breakout_policy_result(break_direction="DOWNWARD_BREAK")
    broken = swing(kind=SwingKind.LOW, price=Decimal("100"))
    br = structural_break(broken_swing=broken, break_close=Decimal("95"), direction=BreakDirection.DOWNWARD_BREAK)
    ms = usable_market_structure(breaks=(br,))
    facts = symbol_facts(ask=Decimal("90.5"), bid=Decimal("90"))

    result = result_for(_construct(policy, market_structure=ms, facts=facts), StrategyFamily.BREAKOUT)

    assert result.outcome is SetupConstructionOutcome.CONSTRUCTED
    assert result.setup.direction is TradeDirection.SHORT
    assert result.setup.entry_price == Decimal("90")
    assert result.setup.stop_loss == Decimal("100")


def test_latest_break_selected_not_first() -> None:
    policy = breakout_policy_result(break_direction="UPWARD_BREAK")
    first_broken = swing(kind=SwingKind.HIGH, price=Decimal("90"), candle_time=AS_OF - timedelta(hours=6))
    first_break = structural_break(broken_swing=first_broken, break_close=Decimal("92"), direction=BreakDirection.UPWARD_BREAK)
    last_broken = swing(kind=SwingKind.HIGH, price=Decimal("100"), candle_time=AS_OF - timedelta(hours=3))
    last_break = structural_break(broken_swing=last_broken, break_close=Decimal("105"), direction=BreakDirection.UPWARD_BREAK)
    # Selection is by tuple POSITION (breaks[-1]), never by re-sorting on
    # break_candle_time - both breaks are independently well-formed and
    # chronologically ordered here only for fixture readability.
    ms = usable_market_structure(breaks=(first_break, last_break))
    facts = symbol_facts(ask=Decimal("110"), bid=Decimal("109.5"))

    result = result_for(_construct(policy, market_structure=ms, facts=facts), StrategyFamily.BREAKOUT)

    assert result.outcome is SetupConstructionOutcome.CONSTRUCTED
    assert result.setup.stop_loss == Decimal("100")  # from last_break, never first_break's 90


def test_direction_mismatch_blocks_missing_stop_reference() -> None:
    # Judge's authorized thesis is SHORT (DOWNWARD_BREAK), but the supplied
    # M15 structure's own latest break is UPWARD - inconsistent.
    policy = breakout_policy_result(break_direction="DOWNWARD_BREAK")
    broken = swing(kind=SwingKind.HIGH, price=Decimal("100"))
    br = structural_break(broken_swing=broken, break_close=Decimal("105"), direction=BreakDirection.UPWARD_BREAK)
    ms = usable_market_structure(breaks=(br,))

    result = result_for(_construct(policy, market_structure=ms), StrategyFamily.BREAKOUT)

    assert result.outcome is SetupConstructionOutcome.BLOCKED
    assert result.reasons == (SetupBlockReason.MISSING_STOP_REFERENCE,)


def test_no_break_blocks_missing_stop_reference() -> None:
    policy = breakout_policy_result(break_direction="UPWARD_BREAK")
    ms = usable_market_structure(breaks=())

    result = result_for(_construct(policy, market_structure=ms), StrategyFamily.BREAKOUT)

    assert result.outcome is SetupConstructionOutcome.BLOCKED
    assert result.reasons == (SetupBlockReason.MISSING_STOP_REFERENCE,)


def test_wrong_side_stop_blocks_invalid_stop_side() -> None:
    policy = breakout_policy_result(break_direction="UPWARD_BREAK")
    # The broken swing's price sits ABOVE the live ask - invalid for a LONG.
    broken = swing(kind=SwingKind.HIGH, price=Decimal("120"))
    br = structural_break(broken_swing=broken, break_close=Decimal("125"), direction=BreakDirection.UPWARD_BREAK)
    ms = usable_market_structure(breaks=(br,))
    facts = symbol_facts(ask=Decimal("110"), bid=Decimal("109.5"))

    result = result_for(_construct(policy, market_structure=ms, facts=facts), StrategyFamily.BREAKOUT)

    assert result.outcome is SetupConstructionOutcome.BLOCKED
    assert result.reasons == (SetupBlockReason.INVALID_STOP_SIDE,)
