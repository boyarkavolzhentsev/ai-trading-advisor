"""Stage 3B must never carry a trading recommendation - enforced structurally.

Mirrors ``tests/test_flow_analysts_no_trading_fields.py`` one contour over:
no BUY/SELL/LONG/SHORT/STRONG/WEAK/EXTREME/UNUSUAL/HIGH/LOW as a bare enum
value, no risk/money/position fields on any Stage 3B model, no Judge/
MarketRegime coupling, and no history/timeframe-comparison parameter on the
public ``TechnicalAnalyst`` interface.
"""

from __future__ import annotations

import ast
import inspect
from enum import Enum
from pathlib import Path

import pytest

from app.core.enums import technical_analysis
from app.core.models.technical_analysis_result import TechnicalAnalysisObservation, TechnicalAnalysisResult
from app.core.models.technical_evidence import TechnicalEvidence
from app.technical_analysts import candle_structure, market_structure, momentum, moving_average, range_state, trend, volatility
from app.technical_analysts.protocols import TechnicalAnalyst

ANALYST_MODULES = (trend, market_structure, volatility, momentum, moving_average, candle_structure, range_state)

FORBIDDEN_BARE_VALUES = {
    "BUY",
    "SELL",
    "LONG",
    "SHORT",
    "STRONG",
    "WEAK",
    "EXTREME",
    "UNUSUAL",
    "HIGH",
    "LOW",
    "CHEAP",
    "EXPENSIVE",
    "OVERBOUGHT",
    "OVERSOLD",
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
    "regime",
    "verdict",
}


def _all_enum_classes():
    return [
        obj
        for name, obj in vars(technical_analysis).items()
        if isinstance(obj, type) and issubclass(obj, Enum) and obj.__module__ == technical_analysis.__name__
    ]


def test_no_forbidden_bare_enum_values() -> None:
    for enum_cls in _all_enum_classes():
        for member in enum_cls:
            assert member.value not in FORBIDDEN_BARE_VALUES, f"{enum_cls.__name__}.{member.name} is a forbidden bare value"


@pytest.mark.parametrize("model", (TechnicalEvidence, TechnicalAnalysisObservation, TechnicalAnalysisResult), ids=lambda m: m.__name__)
def test_no_forbidden_model_fields(model) -> None:
    offending = set(model.model_fields) & FORBIDDEN_MODEL_FIELDS
    assert offending == set(), f"{model.__name__} carries forbidden field(s): {offending}"


def _source(module) -> str:
    return Path(inspect.getfile(module)).read_text(encoding="utf-8")


@pytest.mark.parametrize("module", ANALYST_MODULES, ids=lambda m: m.__name__)
def test_no_judge_or_regime_vocabulary_in_source(module) -> None:
    lowered = _source(module).lower()
    for forbidden in ("judge", "marketregime", "mt5", "strategy_router"):
        assert forbidden not in lowered, f"{module.__name__} references forbidden term {forbidden!r}"


def test_protocol_has_no_history_parameter() -> None:
    signature = inspect.signature(TechnicalAnalyst.analyze)
    param_names = set(signature.parameters) - {"self"}
    assert param_names == {"snapshot"}


def test_no_llm_vocabulary_anywhere_in_stage_3b() -> None:
    modules = ANALYST_MODULES + (
        __import__("app.technical_analysts.base", fromlist=["base"]),
        __import__("app.technical_analysts.protocols", fromlist=["protocols"]),
    )
    for module in modules:
        lowered = _source(module).lower()
        for forbidden in ("openai", "anthropic", "llm", "prompt", "chat_completion"):
            assert forbidden not in lowered, f"{module.__name__} references forbidden LLM term {forbidden!r}"
