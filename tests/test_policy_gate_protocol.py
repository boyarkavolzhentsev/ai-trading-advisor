"""Stage 6C ``PolicyGateProtocol`` is runtime-checkable and ``PolicyGate``
satisfies it structurally."""

from __future__ import annotations

import inspect

from app.decision.gate import PolicyGate
from app.decision.protocols import PolicyGateProtocol


def test_policy_gate_satisfies_protocol() -> None:
    assert isinstance(PolicyGate(), PolicyGateProtocol)


def test_protocol_is_runtime_checkable() -> None:
    assert getattr(PolicyGateProtocol, "_is_runtime_protocol", False) is True


def test_protocol_apply_signature_has_no_extra_parameters() -> None:
    signature = inspect.signature(PolicyGateProtocol.apply)
    params = list(signature.parameters)
    assert params == ["self", "strategy_judge_result"]
    assert signature.parameters["strategy_judge_result"].kind is inspect.Parameter.KEYWORD_ONLY
