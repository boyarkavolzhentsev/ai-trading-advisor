"""Stage 5A Flow/Technical scope-validation tests.

A mismatched Flow/Technical result is a hard ``ScopeMismatchError`` - never
silently downgraded to a ``MISSING`` contour.

Flow is validated against ``context.symbol`` (the Binance analytical
identity Flow is itself keyed by - unchanged). Technical is validated
against the caller's own explicit ``expected_technical_symbol`` (the
MT5/broker-facing symbol - corrective review, "PROVIDER-AWARE SYMBOL SCOPE
VALIDATION") - never against ``context.symbol``, which is a different
provider's identity. The dedicated non-colliding-pair section below exists
specifically so this coverage can never again be satisfied by an accidental
``"BTCUSDt".upper() == "BTCUSDT"``-style collision between a Binance and an
MT5 symbol spelling.
"""

from __future__ import annotations

import pytest

from app.core.enums.instrument import ContractType
from app.market_evaluation.errors import ScopeMismatchError
from app.market_evaluation.evaluator import MarketEvaluator
from tests.market_evaluation_support import (
    MT5_SYMBOL,
    NOW,
    OTHER_CONTRACT_TYPE,
    OTHER_MT5_SYMBOL,
    OTHER_SYMBOL,
    SYMBOL,
    full_flow_result,
    full_technical_result,
    make_context,
)


def test_flow_symbol_mismatch_raises_scope_mismatch_error() -> None:
    flow = full_flow_result(symbol=OTHER_SYMBOL)
    with pytest.raises(ScopeMismatchError):
        MarketEvaluator().evaluate(
            flow=flow, technical=None, external=None, context=make_context(), evaluation_time=NOW, expected_technical_symbol=SYMBOL
        )


def test_flow_contract_type_mismatch_raises_scope_mismatch_error() -> None:
    flow = full_flow_result(contract_type=OTHER_CONTRACT_TYPE)
    with pytest.raises(ScopeMismatchError):
        MarketEvaluator().evaluate(
            flow=flow, technical=None, external=None, context=make_context(), evaluation_time=NOW, expected_technical_symbol=SYMBOL
        )


def test_technical_symbol_mismatch_raises_scope_mismatch_error() -> None:
    """Technical is validated against ``expected_technical_symbol``, never
    against ``context.symbol`` - a Technical result whose symbol does not
    match the caller's own expected MT5 symbol must still raise, even though
    ``context.symbol`` here is a completely different (Binance) identity by
    design."""
    technical = full_technical_result(symbol=OTHER_MT5_SYMBOL)
    with pytest.raises(ScopeMismatchError):
        MarketEvaluator().evaluate(
            flow=None,
            technical=technical,
            external=None,
            context=make_context(symbol=SYMBOL),
            evaluation_time=NOW,
            expected_technical_symbol=MT5_SYMBOL,
        )


def test_technical_contract_type_mismatch_raises_scope_mismatch_error() -> None:
    technical = full_technical_result(symbol=MT5_SYMBOL, contract_type=OTHER_CONTRACT_TYPE)
    with pytest.raises(ScopeMismatchError):
        MarketEvaluator().evaluate(
            flow=None,
            technical=technical,
            external=None,
            context=make_context(symbol=SYMBOL),
            evaluation_time=NOW,
            expected_technical_symbol=MT5_SYMBOL,
        )


def test_flow_matching_scope_is_accepted() -> None:
    flow = full_flow_result()
    result = MarketEvaluator().evaluate(
        flow=flow, technical=None, external=None, context=make_context(), evaluation_time=NOW, expected_technical_symbol=SYMBOL
    )
    assert result.flow is flow


def test_technical_matching_scope_is_accepted() -> None:
    technical = full_technical_result(symbol=MT5_SYMBOL)
    result = MarketEvaluator().evaluate(
        flow=None,
        technical=technical,
        external=None,
        context=make_context(symbol=SYMBOL),
        evaluation_time=NOW,
        expected_technical_symbol=MT5_SYMBOL,
    )
    assert result.technical is technical


def test_mismatch_is_not_silently_downgraded_to_missing() -> None:
    """A mismatched Flow result must raise, never simply appear as MISSING."""
    flow = full_flow_result(symbol=OTHER_SYMBOL)
    with pytest.raises(ScopeMismatchError):
        MarketEvaluator().evaluate(
            flow=flow, technical=None, external=None, context=make_context(), evaluation_time=NOW, expected_technical_symbol=SYMBOL
        )


# --------------------------------------------------------------------------- #
# Provider-aware symbol-scope regression: deliberately non-colliding pair
#
# binance_symbol = SYMBOL = "BTCUSDT"
# mt5_symbol     = MT5_SYMBOL = "BTCUSD.m"  ("BTCUSD.m".upper() == "BTCUSD.M",
#                                            which is NOT equal to "BTCUSDT")
#
# This pair is chosen specifically so none of these assertions could ever
# pass by the same accidental uppercase collision that masked the original
# defect for the real V1 pair (BTCUSDt/BTCUSDT). If the old
# ``technical.symbol == context.symbol`` invariant were still in place, test
# A below would fail - proving this section actually exercises the fix.
# --------------------------------------------------------------------------- #


def test_A_correct_cross_provider_pair_is_accepted() -> None:
    flow = full_flow_result(symbol=SYMBOL)
    technical = full_technical_result(symbol=MT5_SYMBOL)
    context = make_context(symbol=SYMBOL)

    result = MarketEvaluator().evaluate(
        flow=flow,
        technical=technical,
        external=None,
        context=context,
        evaluation_time=NOW,
        expected_technical_symbol=MT5_SYMBOL,
    )

    assert result.flow is flow
    assert result.technical is technical
    assert result.context.symbol == SYMBOL
    assert result.technical.symbol != result.context.symbol  # the whole point: never required to be equal


def test_B_wrong_technical_symbol_is_rejected() -> None:
    flow = full_flow_result(symbol=SYMBOL)
    technical = full_technical_result(symbol=OTHER_MT5_SYMBOL)  # "ETHUSD.m" - genuinely the wrong instrument
    context = make_context(symbol=SYMBOL)

    with pytest.raises(ScopeMismatchError):
        MarketEvaluator().evaluate(
            flow=flow,
            technical=technical,
            external=None,
            context=context,
            evaluation_time=NOW,
            expected_technical_symbol=MT5_SYMBOL,
        )


def test_C_flow_mismatch_still_rejected_with_noncolliding_pair() -> None:
    flow = full_flow_result(symbol=OTHER_SYMBOL)  # "ETHUSDT" - wrong Binance instrument
    technical = full_technical_result(symbol=MT5_SYMBOL)
    context = make_context(symbol=SYMBOL)

    with pytest.raises(ScopeMismatchError):
        MarketEvaluator().evaluate(
            flow=flow,
            technical=technical,
            external=None,
            context=context,
            evaluation_time=NOW,
            expected_technical_symbol=MT5_SYMBOL,
        )


def test_D_technical_contract_type_mismatch_rejected_with_noncolliding_pair() -> None:
    technical = full_technical_result(symbol=MT5_SYMBOL, contract_type=OTHER_CONTRACT_TYPE)
    context = make_context(symbol=SYMBOL)

    with pytest.raises(ScopeMismatchError):
        MarketEvaluator().evaluate(
            flow=None,
            technical=technical,
            external=None,
            context=context,
            evaluation_time=NOW,
            expected_technical_symbol=MT5_SYMBOL,
        )


def test_E_flow_contract_type_mismatch_rejected_with_noncolliding_pair() -> None:
    flow = full_flow_result(symbol=SYMBOL, contract_type=OTHER_CONTRACT_TYPE)
    context = make_context(symbol=SYMBOL)

    with pytest.raises(ScopeMismatchError):
        MarketEvaluator().evaluate(
            flow=flow,
            technical=None,
            external=None,
            context=context,
            evaluation_time=NOW,
            expected_technical_symbol=MT5_SYMBOL,
        )
