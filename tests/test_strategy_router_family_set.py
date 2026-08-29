"""Stage 6A ``StrategyFamily`` set is pinned exactly.

An accidental addition/removal/reorder of a family must fail loudly here
rather than silently changing every downstream eligibility contract.
"""

from __future__ import annotations

from app.core.enums.strategy_router import StrategyFamily


def test_exact_family_set() -> None:
    assert {member.value for member in StrategyFamily} == {
        "TREND_FOLLOWING",
        "MEAN_REVERSION",
        "BREAKOUT",
        "EVENT_DRIVEN",
    }


def test_canonical_declaration_order() -> None:
    assert tuple(StrategyFamily) == (
        StrategyFamily.TREND_FOLLOWING,
        StrategyFamily.MEAN_REVERSION,
        StrategyFamily.BREAKOUT,
        StrategyFamily.EVENT_DRIVEN,
    )
