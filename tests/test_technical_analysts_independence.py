"""Architecture tests: analyst independence, statelessness, no shared mutation.

Mirrors ``tests/test_flow_analysts_independence.py`` one contour over:
verifies no Stage 3B analyst imports another analyst module, no analyst
module carries mutable global state, no analyst instance carries state after
construction, and every ``analyze`` signature is synchronous with no
history/timeframe-comparison parameter.
"""

from __future__ import annotations

import ast
import inspect
from decimal import Decimal
from pathlib import Path

import pytest

from app.technical_analysts import candle_structure, market_structure, momentum, moving_average, range_state, trend, volatility
from app.technical_analysts.candle_structure import CandleStructureAnalyst
from app.technical_analysts.market_structure import MarketStructureAnalyst
from app.technical_analysts.momentum import MomentumAnalyst
from app.technical_analysts.moving_average import MovingAverageAnalyst
from app.technical_analysts.range_state import RangeStateAnalyst
from app.technical_analysts.trend import TrendAnalyst
from app.technical_analysts.volatility import VolatilityAnalyst

ANALYST_MODULES = (trend, market_structure, volatility, momentum, moving_average, candle_structure, range_state)
ANALYST_CLASSES = (
    TrendAnalyst,
    MarketStructureAnalyst,
    VolatilityAnalyst,
    MomentumAnalyst,
    MovingAverageAnalyst,
    CandleStructureAnalyst,
    RangeStateAnalyst,
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
        and not isinstance(value, (str, int, float, Decimal, tuple, frozenset, type(None)))
    }
    assert forbidden_globals == {}


@pytest.mark.parametrize("analyst_cls", ANALYST_CLASSES, ids=lambda c: c.__name__)
def test_analyst_has_no_instance_state_after_construction(analyst_cls) -> None:
    instance = analyst_cls()
    assert vars(instance) == {}


@pytest.mark.parametrize("analyst_cls", ANALYST_CLASSES, ids=lambda c: c.__name__)
def test_analyze_signature_has_no_history_or_timeframe_comparison_parameter(analyst_cls) -> None:
    signature = inspect.signature(analyst_cls.analyze)
    param_names = set(signature.parameters) - {"self"}
    assert param_names == {"snapshot"}


@pytest.mark.parametrize("analyst_cls", ANALYST_CLASSES, ids=lambda c: c.__name__)
def test_analyze_is_synchronous(analyst_cls) -> None:
    assert not inspect.iscoroutinefunction(analyst_cls.analyze)
