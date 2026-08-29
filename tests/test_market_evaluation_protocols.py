"""Stage 5A protocol conformance tests.

``MarketEvaluationProtocol`` is runtime-checkable, exposes only
``evaluate()``, and ``MarketEvaluator`` structurally satisfies it.
"""

from __future__ import annotations

import typing

from app.market_evaluation.evaluator import MarketEvaluator
from app.market_evaluation.protocols import MarketEvaluationProtocol


def test_protocol_is_runtime_checkable() -> None:
    assert typing.runtime_checkable(MarketEvaluationProtocol) is MarketEvaluationProtocol
    assert isinstance(MarketEvaluator(), MarketEvaluationProtocol)


def test_protocol_exposes_only_evaluate() -> None:
    public_methods = {name for name in vars(MarketEvaluationProtocol) if not name.startswith("_")}
    assert public_methods == {"evaluate"}
