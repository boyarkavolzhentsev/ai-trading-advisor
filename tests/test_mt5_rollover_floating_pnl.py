"""Stage 10B ``MT5AccountFacts.floating_pnl`` amendment: sourced only from
``account_info.profit``, signed, no fabricated zero fallback, no position
read, no protocol extension."""

from __future__ import annotations

import inspect
from decimal import Decimal

import app.mt5.client as client_module
from app.mt5.client import MT5Client
from app.mt5.protocols import MT5ClientProtocol
from tests.mt5_support import FakeRawMT5Module, default_account_info


def test_floating_pnl_positive_normalized() -> None:
    raw = FakeRawMT5Module(account_info=default_account_info(profit=1234.56))
    client = MT5Client(mt5_module=raw)
    client.initialize()
    facts = client.account_facts()
    assert facts is not None
    assert facts.floating_pnl == Decimal("1234.56")


def test_floating_pnl_negative_normalized() -> None:
    raw = FakeRawMT5Module(account_info=default_account_info(profit=-987.65))
    client = MT5Client(mt5_module=raw)
    client.initialize()
    facts = client.account_facts()
    assert facts is not None
    assert facts.floating_pnl == Decimal("-987.65")


def test_floating_pnl_legitimate_zero_normalized() -> None:
    raw = FakeRawMT5Module(account_info=default_account_info(profit=0.0))
    client = MT5Client(mt5_module=raw)
    client.initialize()
    facts = client.account_facts()
    assert facts is not None
    assert facts.floating_pnl == Decimal("0")


def test_floating_pnl_decimal_conversion_avoids_float_repr_artifacts() -> None:
    raw = FakeRawMT5Module(account_info=default_account_info(profit=125.30))
    client = MT5Client(mt5_module=raw)
    client.initialize()
    facts = client.account_facts()
    assert facts is not None
    assert facts.floating_pnl == Decimal("125.3")


def test_account_facts_returns_none_when_unavailable_unchanged() -> None:
    """Existing Stage 10A behavior preserved: account_info() unavailable
    still yields None, never a fabricated/partial MT5AccountFacts."""
    raw = FakeRawMT5Module(account_info=None)
    client = MT5Client(mt5_module=raw)
    client.initialize()
    assert client.account_facts() is None


def test_client_source_has_no_zero_fallback_for_floating_pnl() -> None:
    source = inspect.getsource(client_module)
    assert "floating_pnl=Decimal(str(account_info.profit))" in source
    assert 'Decimal("0") if' not in source
    assert "or Decimal(0)" not in source


def test_client_source_never_reads_positions_for_floating_pnl() -> None:
    source = inspect.getsource(client_module)
    assert "positions_get" not in source
    assert "history_deals" not in source


def test_protocol_still_exposes_exactly_four_methods() -> None:
    members = {name for name, _ in inspect.getmembers(MT5ClientProtocol) if not name.startswith("_")}
    assert members == {"initialize", "runtime_status", "account_facts", "shutdown"}
