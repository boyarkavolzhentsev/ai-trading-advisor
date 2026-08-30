"""Stage 8: allocation is order-independent and shows no family preference -
symmetric ceilings under scaling produce symmetric (equal) allocations
regardless of canonical family order."""

from __future__ import annotations

from decimal import Decimal

import ast
import inspect
from pathlib import Path

from app.core.enums.portfolio import PortfolioFamilyVerdict
from app.diversification.supervisor import PortfolioSupervisor
from tests.market_evaluation_support import full_flow_result, make_context
from tests.portfolio_support import route_judge_gate_risk_and_portfolio, technical_with_trend_and_confirmed_break
from tests.risk_gate_support import default_account_snapshot
from tests.strategy_judge_support import external_with_news_sentiment


def test_symmetric_ceilings_yield_symmetric_allocations() -> None:
    """TREND_FOLLOWING, BREAKOUT and EVENT_DRIVEN all present identical
    max_individual_risk ceilings (same risk_per_unit, same per-trade
    budget) - scaling must treat every one of them identically, with no
    family favored regardless of its position in canonical order."""
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
    eligible = [r for r in portfolio_result.family_results if r.verdict is PortfolioFamilyVerdict.ELIGIBLE_FOR_SESSION_REVIEW]
    allocations = {r.portfolio_allocated_risk for r in eligible}
    # Every eligible family had the identical ceiling (5000) - all allocations must be identical too.
    assert len(allocations) == 1


def test_source_has_no_ranking_voting_or_priority_construct() -> None:
    """AST-based, not a substring scan: inspects actual calls/identifiers in
    the code only, avoiding false positives on prose in docstrings."""
    path = Path(inspect.getfile(PortfolioSupervisor))
    tree = ast.parse(path.read_text(encoding="utf-8"))
    forbidden_call_names = {"Counter", "sorted"}
    forbidden_attrs = {"count"}
    forbidden_identifiers = {"vote", "votes", "majority", "weight", "weights", "rank", "ranking", "priority", "score", "confidence"}

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in forbidden_call_names:
                raise AssertionError(f"supervisor.py calls forbidden aggregation construct: {func.id}(...)")
            if isinstance(func, ast.Attribute) and func.attr in forbidden_attrs:
                raise AssertionError(f"supervisor.py calls forbidden .{func.attr}(...)")
        if isinstance(node, ast.Name) and node.id in forbidden_identifiers:
            raise AssertionError(f"supervisor.py uses forbidden identifier name {node.id!r}")
        if isinstance(node, ast.arg) and node.arg in forbidden_identifiers:
            raise AssertionError(f"supervisor.py uses forbidden parameter name {node.arg!r}")
