"""Stage 5A Flow/Technical scope-validation tests.

A mismatched Flow/Technical result is a hard ``ScopeMismatchError`` - never
silently downgraded to a ``MISSING`` contour.
"""

from __future__ import annotations

import pytest

from app.core.enums.instrument import ContractType
from app.market_evaluation.errors import ScopeMismatchError
from app.market_evaluation.evaluator import MarketEvaluator
from tests.market_evaluation_support import (
    NOW,
    OTHER_CONTRACT_TYPE,
    OTHER_SYMBOL,
    full_flow_result,
    full_technical_result,
    make_context,
)


def test_flow_symbol_mismatch_raises_scope_mismatch_error() -> None:
    flow = full_flow_result(symbol=OTHER_SYMBOL)
    with pytest.raises(ScopeMismatchError):
        MarketEvaluator().evaluate(flow=flow, technical=None, external=None, context=make_context(), evaluation_time=NOW)


def test_flow_contract_type_mismatch_raises_scope_mismatch_error() -> None:
    flow = full_flow_result(contract_type=OTHER_CONTRACT_TYPE)
    with pytest.raises(ScopeMismatchError):
        MarketEvaluator().evaluate(flow=flow, technical=None, external=None, context=make_context(), evaluation_time=NOW)


def test_technical_symbol_mismatch_raises_scope_mismatch_error() -> None:
    technical = full_technical_result(symbol=OTHER_SYMBOL)
    with pytest.raises(ScopeMismatchError):
        MarketEvaluator().evaluate(
            flow=None, technical=technical, external=None, context=make_context(), evaluation_time=NOW
        )


def test_technical_contract_type_mismatch_raises_scope_mismatch_error() -> None:
    technical = full_technical_result(contract_type=OTHER_CONTRACT_TYPE)
    with pytest.raises(ScopeMismatchError):
        MarketEvaluator().evaluate(
            flow=None, technical=technical, external=None, context=make_context(), evaluation_time=NOW
        )


def test_flow_matching_scope_is_accepted() -> None:
    flow = full_flow_result()
    result = MarketEvaluator().evaluate(
        flow=flow, technical=None, external=None, context=make_context(), evaluation_time=NOW
    )
    assert result.flow is flow


def test_technical_matching_scope_is_accepted() -> None:
    technical = full_technical_result()
    result = MarketEvaluator().evaluate(
        flow=None, technical=technical, external=None, context=make_context(), evaluation_time=NOW
    )
    assert result.technical is technical


def test_mismatch_is_not_silently_downgraded_to_missing() -> None:
    """A mismatched Flow result must raise, never simply appear as MISSING."""
    flow = full_flow_result(symbol=OTHER_SYMBOL)
    with pytest.raises(ScopeMismatchError):
        MarketEvaluator().evaluate(flow=flow, technical=None, external=None, context=make_context(), evaluation_time=NOW)
