"""Stage 10A raw ``ACCOUNT_MARGIN_MODE_*`` -> ``AccountPositionMode``
normalization: all three real raw values plus an unrecognized future value."""

from __future__ import annotations

from app.core.enums.mt5_runtime import AccountPositionMode
from app.mt5.client import MT5Client
from tests.mt5_support import FakeRawMT5Module, default_account_info


def _margin_mode_for(raw_value: int) -> AccountPositionMode:
    raw = FakeRawMT5Module(account_info=default_account_info(margin_mode=raw_value))
    client = MT5Client(mt5_module=raw)
    client.initialize()
    facts = client.account_facts()
    assert facts is not None
    return facts.margin_mode


def test_retail_hedging_maps_to_hedging() -> None:
    assert _margin_mode_for(FakeRawMT5Module.ACCOUNT_MARGIN_MODE_RETAIL_HEDGING) is AccountPositionMode.HEDGING


def test_retail_netting_maps_to_netting() -> None:
    assert _margin_mode_for(FakeRawMT5Module.ACCOUNT_MARGIN_MODE_RETAIL_NETTING) is AccountPositionMode.NETTING


def test_exchange_maps_to_netting() -> None:
    assert _margin_mode_for(FakeRawMT5Module.ACCOUNT_MARGIN_MODE_EXCHANGE) is AccountPositionMode.NETTING


def test_unknown_raw_value_maps_to_unknown_without_raising() -> None:
    assert _margin_mode_for(9999) is AccountPositionMode.UNKNOWN


def test_negative_unknown_raw_value_maps_to_unknown_without_raising() -> None:
    assert _margin_mode_for(-1) is AccountPositionMode.UNKNOWN
