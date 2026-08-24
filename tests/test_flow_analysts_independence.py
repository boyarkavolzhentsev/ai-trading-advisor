"""Architecture tests: analyst independence, statelessness, no shared mutation.

Verifies structural properties the Stage 2B design requires: no analyst
imports another analyst, no analyst module carries mutable global state, and
running one analyst never mutates the ``FlowFeatureSnapshot`` it reads or
leaks state into a later, unrelated call.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from app.core.enums.order import OrderSide
from app.flow_analysts import funding, liquidation, open_interest, order_book, price_flow_relationship, taker_flow
from app.flow_analysts.funding import FundingAnalyst
from app.flow_analysts.liquidation import LiquidationAnalyst
from app.flow_analysts.open_interest import OpenInterestAnalyst
from app.flow_analysts.order_book import OrderBookLiquidityAnalyst
from app.flow_analysts.price_flow_relationship import PriceFlowRelationshipAnalyst
from app.flow_analysts.taker_flow import TakerFlowAnalyst
from tests.flow_analysts_support import WINDOW_10S, build_snapshot, make_engine, trade

ANALYST_MODULES = (taker_flow, liquidation, order_book, open_interest, funding, price_flow_relationship)
ANALYST_CLASSES = (
    TakerFlowAnalyst,
    LiquidationAnalyst,
    OrderBookLiquidityAnalyst,
    OpenInterestAnalyst,
    FundingAnalyst,
    PriceFlowRelationshipAnalyst,
)
ANALYST_MODULE_NAMES = {module.__name__ for module in ANALYST_MODULES}


def _imported_module_names(module) -> set[str]:
    source = Path(inspect.getfile(module)).read_text(encoding="utf-8")
    tree = ast.parse(source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


@pytest.mark.parametrize("module", ANALYST_MODULES, ids=lambda m: m.__name__)
def test_no_analyst_imports_another_analyst_module(module) -> None:
    imported = _imported_module_names(module)
    other_analyst_modules = ANALYST_MODULE_NAMES - {module.__name__}
    assert imported.isdisjoint(other_analyst_modules)


@pytest.mark.parametrize("module", ANALYST_MODULES, ids=lambda m: m.__name__)
def test_no_mutable_module_level_state(module) -> None:
    forbidden_globals = {
        name: value
        for name, value in vars(module).items()
        if name not in {"annotations"}
        and not name.startswith("_")
        and not inspect.ismodule(value)
        and not inspect.isclass(value)
        and not inspect.isfunction(value)
        and not isinstance(value, (str, int, float, tuple, frozenset, type(None)))
    }
    assert forbidden_globals == {}


@pytest.mark.parametrize("analyst_cls", ANALYST_CLASSES, ids=lambda c: c.__name__)
def test_analyst_has_no_instance_state_after_construction(analyst_cls) -> None:
    instance = analyst_cls()
    assert vars(instance) == {}


@pytest.mark.parametrize("analyst_cls", ANALYST_CLASSES, ids=lambda c: c.__name__)
def test_analyze_signature_has_no_history_parameter(analyst_cls) -> None:
    signature = inspect.signature(analyst_cls.analyze)
    assert set(signature.parameters) == {"self", "snapshot"}


def test_snapshot_not_mutated_across_multiple_analysts() -> None:
    engine = make_engine(windows=(WINDOW_10S,))
    engine.record_trade(trade(seconds_ago=1, side=OrderSide.BUY, price="100", quantity="1", trade_id=1))
    snapshot = build_snapshot(engine)
    before = snapshot.model_copy(deep=True)

    for analyst_cls in ANALYST_CLASSES:
        analyst_cls().analyze(snapshot)

    assert snapshot == before


def test_analysts_fail_independently_one_broken_snapshot_does_not_affect_others() -> None:
    engine = make_engine(windows=(WINDOW_10S,))
    engine.record_trade(trade(seconds_ago=1, side=OrderSide.BUY, price="100", quantity="1", trade_id=1))
    snapshot = build_snapshot(engine)

    results = {analyst_cls.__name__: analyst_cls().analyze(snapshot) for analyst_cls in ANALYST_CLASSES}
    assert len(results) == len(ANALYST_CLASSES)
    assert all(result.symbol == "BTCUSDT" for result in results.values())
