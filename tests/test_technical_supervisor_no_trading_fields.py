"""Stage 3C must never carry a trading recommendation - enforced structurally.

Mirrors ``tests/test_flow_supervisor_no_trading_fields.py`` one contour over:
no ``TradeDirection`` import, no BUY/SELL/LONG/SHORT/... as a bare enum
value, no risk/money/position/score/weight fields on any Stage 3C model, no
history parameter on the public ``TechnicalSupervisorProtocol``, and a
synchronous-only aggregation entry point with no retained state.
"""

from __future__ import annotations

import ast
import enum
import inspect
from pathlib import Path

import pytest

from app.core.enums import technical_supervisor as technical_supervisor_enums
from app.core.models.technical_supervisor_result import TechnicalSupervisorResult
from app.technical_supervisor import errors, supervisor
from app.technical_supervisor.protocols import TechnicalSupervisorProtocol
from app.technical_supervisor.supervisor import TechnicalSupervisor

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
    "technical_direction",
    "technical_score",
    "technical_strength",
    "timeframe_weight",
    "timeframe_weights",
    "analyst_weight",
    "analyst_weights",
}


def _all_enum_classes():
    return [
        obj
        for name, obj in vars(technical_supervisor_enums).items()
        if isinstance(obj, type) and issubclass(obj, enum.Enum) and obj.__module__ == technical_supervisor_enums.__name__
    ]


def test_no_forbidden_bare_enum_values() -> None:
    offenders = []
    for enum_cls in _all_enum_classes():
        for member in enum_cls:
            if member.value in FORBIDDEN_BARE_VALUES:
                offenders.append(f"{enum_cls.__name__}.{member.name}={member.value!r}")
    assert offenders == [], f"forbidden bare trading/magnitude vocabulary found: {offenders}"


def test_technical_supervisor_result_has_no_trading_fields() -> None:
    assert FORBIDDEN_MODEL_FIELDS.isdisjoint(TechnicalSupervisorResult.model_fields)


def test_technical_supervisor_result_has_no_free_text_verdict_field() -> None:
    assert "summary" not in TechnicalSupervisorResult.model_fields
    assert "verdict" not in TechnicalSupervisorResult.model_fields


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
    for field_info in TechnicalSupervisorResult.model_fields.values():
        assert "TradeDirection" not in str(field_info.annotation)


def test_technical_supervisor_protocol_has_no_history_parameter() -> None:
    signature = inspect.signature(TechnicalSupervisorProtocol.aggregate)
    assert set(signature.parameters) == {"self", "results"}


def test_protocol_aggregate_is_synchronous() -> None:
    assert not inspect.iscoroutinefunction(TechnicalSupervisorProtocol.aggregate)


def test_supervisor_aggregate_is_synchronous() -> None:
    assert not inspect.iscoroutinefunction(TechnicalSupervisor.aggregate)


def test_supervisor_holds_no_history_or_cache_state() -> None:
    instance = TechnicalSupervisor()
    assert set(vars(instance)) == {"_expected_analysts", "_expected_timeframes"}
