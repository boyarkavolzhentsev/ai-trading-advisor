"""Stage 5A ``MarketEvaluationContext`` validation tests.

Every mapping field is independent, optional, and never derived from
another field - only the on-chain ``(base_asset, network)`` pairing is
enforced.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.enums.instrument import ContractType
from app.core.models.market_evaluation_context import MarketEvaluationContext
from tests.market_evaluation_support import ASSET, CURRENCY, NETWORK, SYMBOL


def test_minimal_context_requires_only_symbol_and_contract_type() -> None:
    context = MarketEvaluationContext(symbol=SYMBOL, contract_type=ContractType.PERPETUAL)
    assert context.base_asset is None
    assert context.network is None
    assert context.currency_exposures == ()


def test_base_asset_and_network_both_supplied_is_valid() -> None:
    context = MarketEvaluationContext(
        symbol=SYMBOL, contract_type=ContractType.PERPETUAL, base_asset=ASSET, network=NETWORK
    )
    assert context.base_asset == ASSET
    assert context.network == NETWORK


def test_base_asset_without_network_is_rejected() -> None:
    with pytest.raises(ValidationError):
        MarketEvaluationContext(symbol=SYMBOL, contract_type=ContractType.PERPETUAL, base_asset=ASSET)


def test_network_without_base_asset_is_rejected() -> None:
    with pytest.raises(ValidationError):
        MarketEvaluationContext(symbol=SYMBOL, contract_type=ContractType.PERPETUAL, network=NETWORK)


def test_currency_exposures_is_independent_of_base_asset_network() -> None:
    context = MarketEvaluationContext(
        symbol=SYMBOL, contract_type=ContractType.PERPETUAL, currency_exposures=(CURRENCY,)
    )
    assert context.currency_exposures == (CURRENCY,)
    assert context.base_asset is None
    assert context.network is None


def test_no_quote_asset_field_exists() -> None:
    assert "quote_asset" not in MarketEvaluationContext.model_fields


def test_no_market_venue_timeframe_fields_exist() -> None:
    forbidden = {"market", "venue", "timeframe"}
    assert forbidden.isdisjoint(MarketEvaluationContext.model_fields)


def test_context_is_frozen() -> None:
    context = MarketEvaluationContext(symbol=SYMBOL, contract_type=ContractType.PERPETUAL)
    with pytest.raises(ValidationError):
        context.symbol = "ETHUSDT"  # type: ignore[misc]


def test_context_forbids_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        MarketEvaluationContext(symbol=SYMBOL, contract_type=ContractType.PERPETUAL, unexpected_field="value")
