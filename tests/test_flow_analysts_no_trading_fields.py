"""Stage 2B must never carry a trading recommendation - enforced structurally.

Covers: no ``TradeDirection`` import, no BUY/SELL/LONG/SHORT/STRONG/WEAK/
EXTREME/UNUSUAL/HIGH/LOW as a bare enum value, no risk/money/position
fields on any Stage 2B model, and no cross-snapshot history parameter on
the public ``FlowAnalyst`` interface (Stage 2B v1 reasons only across the
windows already contained in one ``FlowFeatureSnapshot``).
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from app.core.enums import flow_analysis
from app.core.models.flow_analysis_result import FlowAnalysisObservation, FlowAnalysisResult
from app.core.models.flow_evidence import FlowEvidence
from app.flow_analysts import funding, liquidation, open_interest, order_book, price_flow_relationship, taker_flow
from app.flow_analysts.protocols import FlowAnalyst

ANALYST_MODULES = (taker_flow, liquidation, order_book, open_interest, funding, price_flow_relationship)

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
}


def _all_enum_classes():
    return [
        obj
        for name, obj in vars(flow_analysis).items()
        if isinstance(obj, type) and issubclass(obj, __import__("enum").Enum) and obj.__module__ == flow_analysis.__name__
    ]


def test_no_forbidden_bare_enum_values() -> None:
    offenders = []
    for enum_cls in _all_enum_classes():
        for member in enum_cls:
            if member.value in FORBIDDEN_BARE_VALUES:
                offenders.append(f"{enum_cls.__name__}.{member.name}={member.value!r}")
    assert offenders == [], f"forbidden bare trading/magnitude vocabulary found: {offenders}"


def test_flow_analysis_result_has_no_trading_fields() -> None:
    assert FORBIDDEN_MODEL_FIELDS.isdisjoint(FlowAnalysisResult.model_fields)
    assert FORBIDDEN_MODEL_FIELDS.isdisjoint(FlowAnalysisObservation.model_fields)
    assert FORBIDDEN_MODEL_FIELDS.isdisjoint(FlowEvidence.model_fields)


def test_flow_analysis_result_has_no_summary_field() -> None:
    assert "summary" not in FlowAnalysisResult.model_fields


@pytest.mark.parametrize("module", ANALYST_MODULES, ids=lambda m: m.__name__)
def test_no_analyst_module_imports_trade_direction(module) -> None:
    source = Path(inspect.getfile(module)).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "app.core.enums.trade":
            pytest.fail(f"{module.__name__} imports from app.core.enums.trade (TradeDirection vocabulary)")
        if isinstance(node, ast.ImportFrom) and node.names:
            for alias in node.names:
                assert alias.name != "TradeDirection"


def test_no_analyst_model_field_types_reference_trade_direction() -> None:
    for field_info in list(FlowAnalysisResult.model_fields.values()) + list(FlowAnalysisObservation.model_fields.values()):
        assert "TradeDirection" not in str(field_info.annotation)


def test_flow_analyst_interface_has_no_history_parameter() -> None:
    signature = inspect.signature(FlowAnalyst.analyze)
    assert set(signature.parameters) == {"self", "snapshot"}
