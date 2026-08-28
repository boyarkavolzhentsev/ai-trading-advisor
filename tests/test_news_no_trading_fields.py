"""Stage 4C must never carry a trading recommendation or interpretation -
enforced structurally, mirroring ``tests/test_rates_no_trading_fields.py``.
"""

from __future__ import annotations

import ast
import inspect
from enum import Enum
from pathlib import Path

import pytest

from app.core.models.news_item import NewsItem
from app.news import exceptions, history, protocols, provenance

MODULES = (exceptions, history, protocols, provenance)

FORBIDDEN_BARE_VALUES = {
    "BUY",
    "SELL",
    "LONG",
    "SHORT",
    "STRONG",
    "WEAK",
    "EXTREME",
    "UNUSUAL",
    "CHEAP",
    "EXPENSIVE",
    "HAWKISH",
    "DOVISH",
    "BULLISH",
    "BEARISH",
}

FORBIDDEN_MODEL_FIELDS = {
    "direction",
    "confidence",
    "stop_loss",
    "take_profit",
    "position_size",
    "risk_percent",
    "entry",
    "target",
    "probability",
    "trading_impact",
}


def _all_enum_classes(module):
    return [
        obj
        for _, obj in vars(module).items()
        if isinstance(obj, type) and issubclass(obj, Enum) and obj.__module__ == module.__name__
    ]


def test_no_forbidden_bare_enum_values() -> None:
    offenders = []
    for enum_cls in _all_enum_classes(provenance):
        for member in enum_cls:
            if member.value in FORBIDDEN_BARE_VALUES:
                offenders.append(f"{enum_cls.__name__}.{member.name}={member.value!r}")
    assert offenders == [], f"forbidden trading/interpretation vocabulary found: {offenders}"


def test_news_item_has_no_trading_fields() -> None:
    assert FORBIDDEN_MODEL_FIELDS.isdisjoint(NewsItem.model_fields)


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_no_news_module_imports_trade_direction(module) -> None:
    source = Path(inspect.getfile(module)).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "app.core.enums.trade":
            pytest.fail(f"{module.__name__} imports from app.core.enums.trade (TradeDirection vocabulary)")
        if isinstance(node, ast.ImportFrom) and node.names:
            for alias in node.names:
                assert alias.name != "TradeDirection"


@pytest.mark.parametrize(
    "forbidden_name",
    ["Judge", "JudgeVerdict", "StrategyRouter", "PositionSize", "TradeSetup", "TradeDecision"],
)
def test_no_judge_or_strategy_vocabulary_in_news_source(forbidden_name: str) -> None:
    for module in MODULES:
        source = Path(inspect.getfile(module)).read_text(encoding="utf-8")
        assert forbidden_name not in source, f"{module.__name__} references forbidden name {forbidden_name!r}"
