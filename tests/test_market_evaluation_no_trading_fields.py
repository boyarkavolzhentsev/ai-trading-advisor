"""Stage 5A must never carry a trading recommendation - enforced structurally.

Mirrors ``tests/test_flow_supervisor_no_trading_fields.py``/
``tests/test_external_intelligence_supervisor_no_trading_fields.py`` one
contour over: no ``TradeDirection`` import, no BUY/SELL/LONG/SHORT/ENTER/
EXIT/HOLD as a bare enum value, no risk/money/position/score/weight/
direction/confidence field on any Stage 5A model, and no history parameter
on the public ``MarketEvaluationProtocol``.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from app.core.enums import market_evaluation as market_evaluation_enums
from app.core.models.market_evaluation_context import MarketEvaluationContext
from app.core.models.market_evaluation_result import ExternalScopeAlignmentRef, MarketEvaluationResult
from app.market_evaluation import errors, evaluator, protocols
from app.market_evaluation.protocols import MarketEvaluationProtocol

MODULES = (errors, evaluator, protocols)

FORBIDDEN_BARE_VALUES = {
    "BUY",
    "SELL",
    "LONG",
    "SHORT",
    "ENTER",
    "EXIT",
    "HOLD",
    "STRONG",
    "WEAK",
    "EXTREME",
    "UNUSUAL",
    "HIGH",
    "LOW",
    "CHEAP",
    "EXPENSIVE",
    "BULLISH",
    "BEARISH",
    "RISK_ON",
    "RISK_OFF",
}

FORBIDDEN_MODEL_FIELDS = {
    "direction",
    "trade_direction",
    "signal",
    "recommendation",
    "action",
    "entry",
    "stop_loss",
    "take_profit",
    "position_size",
    "risk",
    "reward",
    "confidence",
    "probability",
    "edge",
    "expected_value",
    "score",
    "weight",
    "vote",
    "rank",
    "strategy",
    "available_contours",
    "missing_contours",
    "partial_contours",
}


def _all_enum_classes():
    return [
        obj
        for name, obj in vars(market_evaluation_enums).items()
        if isinstance(obj, type)
        and issubclass(obj, __import__("enum").Enum)
        and obj.__module__ == market_evaluation_enums.__name__
    ]


def test_no_forbidden_bare_enum_values() -> None:
    offenders = []
    for enum_cls in _all_enum_classes():
        for member in enum_cls:
            if member.value in FORBIDDEN_BARE_VALUES:
                offenders.append(f"{enum_cls.__name__}.{member.name}={member.value!r}")
    assert offenders == [], f"forbidden bare trading/magnitude vocabulary found: {offenders}"


def test_result_has_no_trading_fields() -> None:
    assert FORBIDDEN_MODEL_FIELDS.isdisjoint(MarketEvaluationResult.model_fields)


def test_context_has_no_trading_fields() -> None:
    assert FORBIDDEN_MODEL_FIELDS.isdisjoint(MarketEvaluationContext.model_fields)


def test_alignment_ref_has_no_trading_fields() -> None:
    assert FORBIDDEN_MODEL_FIELDS.isdisjoint(ExternalScopeAlignmentRef.model_fields)


def test_result_has_no_free_text_explanation_field() -> None:
    assert "summary" not in MarketEvaluationResult.model_fields
    assert "verdict" not in MarketEvaluationResult.model_fields
    assert "explanation" not in MarketEvaluationResult.model_fields
    assert "reasoning" not in MarketEvaluationResult.model_fields


def test_result_has_no_generic_metadata_dict() -> None:
    assert "metadata" not in MarketEvaluationResult.model_fields
    assert "provenance" not in MarketEvaluationResult.model_fields


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


def test_no_model_field_types_reference_trade_direction() -> None:
    for field_info in MarketEvaluationResult.model_fields.values():
        assert "TradeDirection" not in str(field_info.annotation)


def test_protocol_has_no_history_parameter() -> None:
    signature = inspect.signature(MarketEvaluationProtocol.evaluate)
    assert set(signature.parameters) == {"self", "flow", "technical", "external", "context", "evaluation_time"}


def test_no_numeric_score_field_anywhere() -> None:
    forbidden_substrings = ("score", "confidence", "weight", "probability")
    for name in MarketEvaluationResult.model_fields:
        for substring in forbidden_substrings:
            assert substring not in name.lower()
