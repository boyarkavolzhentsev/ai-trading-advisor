"""Stage 10B ``MT5AccountFacts.floating_pnl`` amendment: sourced only from
``account_info.profit``, signed, no fabricated zero fallback, and (at the
time of Stage 10B) no protocol extension. Stage 10C later adds ``positions()``/
``symbol_facts()`` to the protocol for its own, unrelated open-risk/sizing
purpose - these tests confirm ``floating_pnl`` specifically never depends on
that position data, not that ``client.py``/the protocol stay frozen forever."""

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


def test_floating_pnl_assignment_does_not_reference_positions() -> None:
    """The floating_pnl assignment itself is sourced only from
    account_info.profit - Stage 10C's later positions_get()/symbol_info()
    reads (added for open-risk/sizing, not floating_pnl) never feed it."""
    source = inspect.getsource(client_module)
    floating_pnl_line = next(line for line in source.splitlines() if "floating_pnl=" in line)
    assert "positions" not in floating_pnl_line
    assert "history_deals" not in source


def test_protocol_exposes_no_history_or_order_methods() -> None:
    members = {name for name, _ in inspect.getmembers(MT5ClientProtocol) if not name.startswith("_")}
    assert members.isdisjoint({"history_deals", "history_orders", "order_send", "order_check"})
