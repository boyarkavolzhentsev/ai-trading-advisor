"""Stage 4G must never carry a trading recommendation - enforced structurally.

Mirrors ``tests/test_flow_supervisor_no_trading_fields.py``/
``tests/test_external_intelligence_no_trading_fields.py`` one contour over:
no ``TradeDirection`` import, no BUY/SELL/LONG/SHORT/... as a bare enum
value, no risk/money/position/score/weight/direction fields on any Stage 4G
model, and no history parameter on the public
``ExternalIntelligenceSupervisorProtocol``.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from app.core.enums import external_intelligence_supervisor as external_intelligence_supervisor_enums
from app.core.models.external_intelligence_supervisor_result import (
    ExternalIntelligenceScopeSummary,
    ExternalIntelligenceSupervisorResult,
)
from app.external_intelligence_supervisor import errors, supervisor
from app.external_intelligence_supervisor.protocols import ExternalIntelligenceSupervisorProtocol

MODULES = (errors, supervisor)

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
    "BULLISH",
    "BEARISH",
    "RISK_ON",
    "RISK_OFF",
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
    "weight",
    "score",
    "recommendation",
    "strength",
    "agreement",
    "contradiction",
    "coherence",
}


def _all_enum_classes():
    return [
        obj
        for name, obj in vars(external_intelligence_supervisor_enums).items()
        if isinstance(obj, type)
        and issubclass(obj, __import__("enum").Enum)
        and obj.__module__ == external_intelligence_supervisor_enums.__name__
    ]


def test_no_forbidden_bare_enum_values() -> None:
    offenders = []
    for enum_cls in _all_enum_classes():
        for member in enum_cls:
            if member.value in FORBIDDEN_BARE_VALUES:
                offenders.append(f"{enum_cls.__name__}.{member.name}={member.value!r}")
    assert offenders == [], f"forbidden bare trading/magnitude vocabulary found: {offenders}"


def test_supervisor_result_has_no_trading_fields() -> None:
    assert FORBIDDEN_MODEL_FIELDS.isdisjoint(ExternalIntelligenceSupervisorResult.model_fields)


def test_scope_summary_has_no_trading_fields() -> None:
    assert FORBIDDEN_MODEL_FIELDS.isdisjoint(ExternalIntelligenceScopeSummary.model_fields)


def test_supervisor_result_has_no_free_text_verdict_field() -> None:
    assert "summary" not in ExternalIntelligenceSupervisorResult.model_fields
    assert "verdict" not in ExternalIntelligenceSupervisorResult.model_fields


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
    for field_info in ExternalIntelligenceSupervisorResult.model_fields.values():
        assert "TradeDirection" not in str(field_info.annotation)


def test_supervisor_protocol_has_no_history_parameter() -> None:
    signature = inspect.signature(ExternalIntelligenceSupervisorProtocol.aggregate)
    assert set(signature.parameters) == {"self", "results", "analysis_time"}


def test_no_scalar_external_score_field() -> None:
    forbidden_names = {"external_score", "external_intelligence_score", "index", "ratio", "usable_ratio"}
    assert forbidden_names.isdisjoint(ExternalIntelligenceSupervisorResult.model_fields)
