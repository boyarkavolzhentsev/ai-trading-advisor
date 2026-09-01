"""Stage 10A ``MT5Client`` connectivity mapping: each ``MT5ConnectivityState``
has exactly one deterministic trigger, only ``AVAILABLE`` returns account
facts, and ``trade_allowed``/``trade_expert`` are facts only - never a
connectivity gate."""

from __future__ import annotations

from decimal import Decimal

from app.core.enums.mt5_runtime import MT5ConnectivityState
from app.mt5.client import MT5Client
from tests.mt5_support import FakeRawMT5Module, default_account_info, default_terminal_info


def test_available_when_terminal_connected_and_account_present() -> None:
    raw = FakeRawMT5Module()
    client = MT5Client(mt5_module=raw)
    status = client.initialize()
    assert status.state is MT5ConnectivityState.AVAILABLE
    assert status.reason is None


def test_initialization_failed_without_credentials() -> None:
    raw = FakeRawMT5Module(initialize_result=False, last_error=(1, "IPC initialize failed"))
    client = MT5Client(mt5_module=raw)
    status = client.initialize()
    assert status.state is MT5ConnectivityState.INITIALIZATION_FAILED
    assert status.reason is not None
    assert "IPC initialize failed" in status.reason


def test_login_failed_with_explicit_credentials() -> None:
    from app.core.models.mt5_runtime import MT5Credentials

    raw = FakeRawMT5Module(initialize_result=False, last_error=(2, "Authorization failed"))
    client = MT5Client(mt5_module=raw, credentials=MT5Credentials(login=12345, password="wrong", server="Broker-Server"))
    status = client.initialize()
    assert status.state is MT5ConnectivityState.LOGIN_FAILED
    assert status.reason is not None


def test_terminal_unavailable_when_terminal_info_none() -> None:
    raw = FakeRawMT5Module(terminal_info=None)
    client = MT5Client(mt5_module=raw)
    status = client.initialize()
    assert status.state is MT5ConnectivityState.TERMINAL_UNAVAILABLE


def test_terminal_unavailable_when_disconnected() -> None:
    raw = FakeRawMT5Module(terminal_info=default_terminal_info(connected=False))
    client = MT5Client(mt5_module=raw)
    status = client.initialize()
    assert status.state is MT5ConnectivityState.TERMINAL_UNAVAILABLE


def test_account_unavailable_when_account_info_none() -> None:
    raw = FakeRawMT5Module(account_info=None)
    client = MT5Client(mt5_module=raw)
    status = client.initialize()
    assert status.state is MT5ConnectivityState.ACCOUNT_UNAVAILABLE


def test_only_available_returns_account_facts() -> None:
    for terminal_info, account_info in (
        (None, default_account_info()),
        (default_terminal_info(connected=False), default_account_info()),
        (default_terminal_info(), None),
    ):
        raw = FakeRawMT5Module(terminal_info=terminal_info, account_info=account_info)
        client = MT5Client(mt5_module=raw)
        client.initialize()
        assert client.account_facts() is None


def test_available_returns_populated_account_facts() -> None:
    raw = FakeRawMT5Module(account_info=default_account_info(equity=54321.0))
    client = MT5Client(mt5_module=raw)
    client.initialize()
    facts = client.account_facts()
    assert facts is not None
    assert facts.equity == Decimal("54321.0")


def test_trade_allowed_false_does_not_change_connectivity_state() -> None:
    raw = FakeRawMT5Module(account_info=default_account_info(trade_allowed=False))
    client = MT5Client(mt5_module=raw)
    status = client.initialize()
    assert status.state is MT5ConnectivityState.AVAILABLE
    facts = client.account_facts()
    assert facts is not None
    assert facts.trade_allowed is False


def test_trade_expert_false_does_not_change_connectivity_state() -> None:
    raw = FakeRawMT5Module(account_info=default_account_info(trade_expert=False))
    client = MT5Client(mt5_module=raw)
    status = client.initialize()
    assert status.state is MT5ConnectivityState.AVAILABLE
    facts = client.account_facts()
    assert facts is not None
    assert facts.trade_expert is False


def test_runtime_status_reflects_state_change_between_calls() -> None:
    raw = FakeRawMT5Module()
    client = MT5Client(mt5_module=raw)
    client.initialize()
    assert client.runtime_status().state is MT5ConnectivityState.AVAILABLE

    raw._terminal_info = default_terminal_info(connected=False)
    assert client.runtime_status().state is MT5ConnectivityState.TERMINAL_UNAVAILABLE
