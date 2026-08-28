"""Stage 4F must never carry a trading recommendation or final direction -
enforced structurally, mirroring ``tests/test_onchain_no_trading_fields.py``.
"""

from __future__ import annotations

import ast
import inspect
from enum import Enum
from pathlib import Path

import pytest

from app.core.enums import external_intelligence_analysis as ei_enums
from app.core.models.external_intelligence_analysis_result import (
    ExternalIntelligenceAnalysisObservation,
    ExternalIntelligenceAnalysisResult,
)
from app.core.models.external_intelligence_evidence import ExternalIntelligenceEvidence
from app.external_intelligence_analysts import base, config, macro_event, news_sentiment, on_chain, protocols, rates_yield

MODULES = (base, config, protocols, macro_event, rates_yield, news_sentiment, on_chain)
MODEL_CLASSES = (ExternalIntelligenceEvidence, ExternalIntelligenceAnalysisObservation, ExternalIntelligenceAnalysisResult)

FORBIDDEN_BARE_VALUES = {
    "BUY",
    "SELL",
    "LONG",
    "SHORT",
    "BULLISH",
    "BEARISH",
    "STRONG",
    "WEAK",
    "EXTREME",
    "UNUSUAL",
    "CHEAP",
    "EXPENSIVE",
    "HAWKISH",
    "DOVISH",
}

FORBIDDEN_MODEL_FIELDS = {
    "direction",
    "confidence",
    "strength",
    "stop_loss",
    "take_profit",
    "position_size",
    "risk_percent",
    "entry",
    "target",
    "probability",
    "trading_impact",
    "recommendation",
    "signal",
    "market_direction",
    "final_score",
}


def _all_enum_classes(module):
    return [
        obj
        for _, obj in vars(module).items()
        if isinstance(obj, type) and issubclass(obj, Enum) and obj.__module__ == module.__name__
    ]


def test_no_forbidden_bare_enum_values() -> None:
    offenders = []
    for enum_cls in _all_enum_classes(ei_enums):
        for member in enum_cls:
            if member.value in FORBIDDEN_BARE_VALUES:
                offenders.append(f"{enum_cls.__name__}.{member.name}={member.value!r}")
    assert offenders == [], f"forbidden trading/interpretation vocabulary found: {offenders}"


@pytest.mark.parametrize("model_cls", MODEL_CLASSES)
def test_model_has_no_trading_fields(model_cls) -> None:
    assert FORBIDDEN_MODEL_FIELDS.isdisjoint(model_cls.model_fields)


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_no_module_imports_trade_direction(module) -> None:
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
    ["Judge", "JudgeVerdict", "StrategyRouter", "PositionSize", "TradeSetup", "TradeDecision", "AgentAssessment"],
)
def test_no_judge_or_strategy_vocabulary_in_source(forbidden_name: str) -> None:
    for module in MODULES:
        source = Path(inspect.getfile(module)).read_text(encoding="utf-8")
        assert forbidden_name not in source, f"{module.__name__} references forbidden name {forbidden_name!r}"
