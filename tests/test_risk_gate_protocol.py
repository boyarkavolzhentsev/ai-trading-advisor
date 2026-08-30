"""Stage 7 ``RiskGateProtocol`` is runtime-checkable and ``RiskGate``
satisfies it structurally."""

from __future__ import annotations

import inspect

from app.risk.engine import RiskGate
from app.risk.protocols import RiskGateProtocol


def test_risk_gate_satisfies_protocol() -> None:
    assert isinstance(RiskGate(), RiskGateProtocol)


def test_protocol_is_runtime_checkable() -> None:
    assert getattr(RiskGateProtocol, "_is_runtime_protocol", False) is True


def test_protocol_evaluate_signature_has_no_extra_parameters() -> None:
    signature = inspect.signature(RiskGateProtocol.evaluate)
    params = list(signature.parameters)
    assert params == ["self", "strategy_policy_result", "account_snapshot", "candidate_inputs", "trading_cycle_config"]
    for name in ("strategy_policy_result", "account_snapshot", "candidate_inputs", "trading_cycle_config"):
        assert signature.parameters[name].kind is inspect.Parameter.KEYWORD_ONLY
