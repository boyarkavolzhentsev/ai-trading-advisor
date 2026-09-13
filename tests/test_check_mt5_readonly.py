"""Tests for the Phase 1 live-read-only MT5 smoke harness
(``scripts/check_mt5_readonly.py``).

The script lives under ``scripts/`` (not a package - no ``__init__.py``, by
this repository's own existing convention for manual check utilities), so
its module is loaded here via ``importlib`` from its file path rather than a
normal package import.

Every test drives ``run_mt5_readonly_smoke`` - the script's pure, injectable
core - against ``tests.runtime_cycle_support.RuntimeCycleFakeClient`` (an
existing fake already implementing ``MT5ClientProtocol`` with call-count
tracking, reused rather than duplicated). No real MT5/MetaTrader5 import,
no real provider access, no live network of any kind.
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import sys
from decimal import Decimal
from pathlib import Path
from types import ModuleType

import pytest

from app.core.enums.mt5_runtime import MT5ConnectivityState
from app.core.models.mt5_runtime import MT5RuntimeStatus
from tests.runtime_cycle_support import AS_OF, RuntimeCycleFakeClient, default_account_facts
from tests.setup_construction_support import symbol_facts

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "check_mt5_readonly.py"


def _load_script_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_mt5_readonly", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses' own type-hint resolution needs cls.__module__ registered
    spec.loader.exec_module(module)
    return module


check_mt5_readonly = _load_script_module()
run_mt5_readonly_smoke = check_mt5_readonly.run_mt5_readonly_smoke

SYMBOL = "BTCUSDt"


def _available_status() -> MT5RuntimeStatus:
    return MT5RuntimeStatus(as_of=AS_OF, state=MT5ConnectivityState.AVAILABLE)


def _client(**overrides: object) -> RuntimeCycleFakeClient:
    fields: dict[str, object] = {
        "runtime_status": _available_status(),
        "account_facts": default_account_facts(),
        "positions_result": ("OK", ()),
        "symbol_facts_by_symbol": {SYMBOL: symbol_facts(symbol=SYMBOL)},
    }
    fields.update(overrides)
    return RuntimeCycleFakeClient(**fields)


# --------------------------------------------------------------------------- #
# A. AVAILABLE happy path
# --------------------------------------------------------------------------- #


def test_available_happy_path_passes() -> None:
    client = _client()
    result = run_mt5_readonly_smoke(client, symbol=SYMBOL)

    assert result.passed is True
    assert result.failure_reasons == ()
    assert result.initialize_state is MT5ConnectivityState.AVAILABLE
    assert result.runtime_status_state is MT5ConnectivityState.AVAILABLE
    assert result.account_facts_available is True
    assert result.account_currency == "USD"
    assert result.positions_status == "OK"
    assert result.position_count == 0
    assert result.symbol_facts_available is True
    assert result.bid == Decimal("100")
    assert result.ask == Decimal("100.10")
    assert result.spread == Decimal("0.10")


# --------------------------------------------------------------------------- #
# B. initialization failure -> FAIL
# --------------------------------------------------------------------------- #


def test_initialization_failure_fails() -> None:
    failed_status = MT5RuntimeStatus(as_of=AS_OF, state=MT5ConnectivityState.INITIALIZATION_FAILED, reason="no terminal")
    client = _client(runtime_status=failed_status)

    result = run_mt5_readonly_smoke(client, symbol=SYMBOL)

    assert result.passed is False
    assert result.initialize_state is MT5ConnectivityState.INITIALIZATION_FAILED
    assert any("initialize()" in reason for reason in result.failure_reasons)
    # Guarded: nothing past initialize() was attempted.
    assert result.runtime_status_state is None
    assert result.account_facts_available is False
    assert result.symbol_facts_available is False


# --------------------------------------------------------------------------- #
# C. account facts unavailable -> FAIL
# --------------------------------------------------------------------------- #


def test_account_facts_unavailable_fails() -> None:
    client = _client(account_facts=None)

    result = run_mt5_readonly_smoke(client, symbol=SYMBOL)

    assert result.passed is False
    assert result.account_facts_available is False
    assert any("account_facts()" in reason for reason in result.failure_reasons)


# --------------------------------------------------------------------------- #
# D. symbol facts unavailable -> FAIL
# --------------------------------------------------------------------------- #


def test_symbol_facts_unavailable_fails() -> None:
    client = _client(symbol_facts_by_symbol={})

    result = run_mt5_readonly_smoke(client, symbol=SYMBOL)

    assert result.passed is False
    assert result.symbol_facts_available is False
    assert any("symbol_facts" in reason for reason in result.failure_reasons)


# --------------------------------------------------------------------------- #
# E. invalid bid/ask -> FAIL
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "overrides,expected_reason_fragment",
    [
        ({"bid": Decimal("0")}, "bid is not > 0"),
        ({"bid": Decimal("100.20"), "ask": Decimal("100.10")}, "ask is not > bid"),
        ({"bid": Decimal("100"), "ask": Decimal("100")}, "ask is not > bid"),
    ],
)
def test_invalid_bid_ask_fails(overrides: dict[str, object], expected_reason_fragment: str) -> None:
    facts = symbol_facts(symbol=SYMBOL, **overrides)
    client = _client(symbol_facts_by_symbol={SYMBOL: facts})

    result = run_mt5_readonly_smoke(client, symbol=SYMBOL)

    assert result.passed is False
    assert any(expected_reason_fragment in reason for reason in result.failure_reasons)


# --------------------------------------------------------------------------- #
# F. invalid broker numeric facts -> FAIL
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "overrides,expected_reason_fragment",
    [
        ({"point": Decimal("0")}, "point is not > 0"),
        ({"trade_tick_size": Decimal("0")}, "trade_tick_size is not > 0"),
        ({"trade_tick_value_loss": Decimal("0")}, "trade_tick_value_loss is not > 0"),
        ({"volume_min": Decimal("0")}, "volume_min is not > 0"),
        ({"volume_min": Decimal("1"), "volume_max": Decimal("0.5")}, "volume_max is not >= volume_min"),
        ({"volume_step": Decimal("0")}, "volume_step is not > 0"),
    ],
)
def test_invalid_broker_numeric_facts_fails(overrides: dict[str, object], expected_reason_fragment: str) -> None:
    facts = symbol_facts(symbol=SYMBOL, **overrides)
    client = _client(symbol_facts_by_symbol={SYMBOL: facts})

    result = run_mt5_readonly_smoke(client, symbol=SYMBOL)

    assert result.passed is False
    assert any(expected_reason_fragment in reason for reason in result.failure_reasons)


# --------------------------------------------------------------------------- #
# G. shutdown occurs on success
# --------------------------------------------------------------------------- #


def test_shutdown_occurs_on_success() -> None:
    client = _client()

    run_mt5_readonly_smoke(client, symbol=SYMBOL)

    assert client.shutdown_calls == 1


# --------------------------------------------------------------------------- #
# H. shutdown occurs on failure/exception
# --------------------------------------------------------------------------- #


def test_shutdown_occurs_on_typed_failure() -> None:
    failed_status = MT5RuntimeStatus(as_of=AS_OF, state=MT5ConnectivityState.TERMINAL_UNAVAILABLE)
    client = _client(runtime_status=failed_status)

    run_mt5_readonly_smoke(client, symbol=SYMBOL)

    assert client.shutdown_calls == 1


def test_shutdown_occurs_on_unexpected_exception() -> None:
    class ExplodingClient(RuntimeCycleFakeClient):
        def account_facts(self):  # type: ignore[override]
            raise RuntimeError("boom")

    client = ExplodingClient(runtime_status=_available_status(), account_facts=default_account_facts())

    with pytest.raises(RuntimeError, match="boom"):
        run_mt5_readonly_smoke(client, symbol=SYMBOL)

    assert client.shutdown_calls == 1


# --------------------------------------------------------------------------- #
# I. no execution/order symbols are imported or referenced (static AST check)
# --------------------------------------------------------------------------- #

_FORBIDDEN_EXECUTION_IDENTIFIERS = {
    "order_send",
    "order_check",
    "OrderSend",
    "OrderCheck",
    "TRADE_ACTION",
    "TRADE_REQUEST",
    "ORDER_TYPE",
    "positions_close",
    "position_close",
    "order_close",
    "order_cancel",
    "order_modify",
    "execute",
    "cancel",
    "modify",
    "close_position",
}
"""Deliberately excludes ``shutdown``/``close`` (real MT5 connection
teardown, not a trading action) and any exact match must be an identifier
this AST walk actually visits (an ``ast.Name``/``ast.Attribute``/import
alias) - never a raw substring match, so a docstring merely mentioning one of
these words in prose can never false-positive this test."""


def _referenced_identifiers(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
            names.update(alias.asname for alias in node.names if alias.asname)
        elif isinstance(node, ast.ImportFrom):
            names.update(alias.name for alias in node.names)
            names.update(alias.asname for alias in node.names if alias.asname)
            if node.module:
                names.add(node.module)
    return names


def test_script_contains_no_forbidden_execution_identifiers() -> None:
    source = _SCRIPT_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    referenced = _referenced_identifiers(tree)

    collision = referenced & _FORBIDDEN_EXECUTION_IDENTIFIERS
    assert not collision, f"scripts/check_mt5_readonly.py references forbidden execution identifiers: {collision}"


def test_script_does_not_import_metatrader5_directly() -> None:
    source = _SCRIPT_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    referenced = _referenced_identifiers(tree)
    assert "MetaTrader5" not in referenced


def test_script_only_calls_the_six_allowed_mt5_client_protocol_methods() -> None:
    """AST-based: every ``client.<attr>(`` call in ``run_mt5_readonly_smoke``
    is one of the six read-only ``MT5ClientProtocol`` methods this Phase 1
    harness is allowed to use."""
    allowed = {"initialize", "runtime_status", "account_facts", "positions", "symbol_facts", "shutdown"}
    source = _SCRIPT_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    called_on_client: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "client"
        ):
            called_on_client.add(node.func.attr)

    assert called_on_client, "expected at least one client.<method>() call in the script"
    assert called_on_client <= allowed, f"unexpected client method calls: {called_on_client - allowed}"


# --------------------------------------------------------------------------- #
# main() CLI exit-code wiring
#
# Every test here monkeypatches only the script's own imported module-level
# seams (``_parse_args``, ``build_mt5_readonly_config_from_env``,
# ``MT5Client``, ``run_mt5_readonly_smoke``) - never anything inside real
# ``MT5Client``/``MetaTrader5``, and no live call of any kind. This closes
# the one disclosed gap from the Phase 1 harness review: nothing previously
# proved ``main()``'s own config-loading/exception-to-exit-code wiring
# actually behaves as documented, only that ``run_mt5_readonly_smoke``
# itself does.
# --------------------------------------------------------------------------- #


class _FakeBootstrapConfig:
    """Stands in for ``app.bootstrap.production.MT5ReadOnlyBootstrapConfig``
    - only the three attributes ``main()`` actually reads are needed."""

    def __init__(self, *, mt5_symbol: str, mt5_path: str | None = None, mt5_credentials: object | None = None) -> None:
        self.mt5_symbol = mt5_symbol
        self.mt5_path = mt5_path
        self.mt5_credentials = mt5_credentials


def _args(symbol: str | None) -> argparse.Namespace:
    return argparse.Namespace(symbol=symbol)


def _canned_result(symbol: str, *, passed: bool) -> object:
    """A real ``check_mt5_readonly.MT5ReadOnlySmokeResult`` (the script's own
    type), never a stand-in - ``main()``'s own ``_print_report``/exit-code
    logic reads real fields off it."""
    return check_mt5_readonly.MT5ReadOnlySmokeResult(
        symbol=symbol,
        initialize_state=MT5ConnectivityState.AVAILABLE if passed else MT5ConnectivityState.INITIALIZATION_FAILED,
        runtime_status_state=MT5ConnectivityState.AVAILABLE if passed else None,
        account_facts_available=passed,
        account_currency="USD" if passed else None,
        positions_status="OK" if passed else "UNAVAILABLE",
        position_count=0 if passed else None,
        symbol_facts_available=passed,
        bid=Decimal("100") if passed else None,
        ask=Decimal("100.10") if passed else None,
        spread=Decimal("0.10") if passed else None,
        point=Decimal("0.00001") if passed else None,
        trade_stops_level=0 if passed else None,
        trade_tick_size=Decimal("0.00001") if passed else None,
        trade_tick_value_loss=Decimal("1") if passed else None,
        volume_min=Decimal("0.01") if passed else None,
        volume_max=Decimal("100") if passed else None,
        volume_step=Decimal("0.01") if passed else None,
        passed=passed,
        failure_reasons=() if passed else ("initialize() did not return AVAILABLE (got INITIALIZATION_FAILED)",),
    )


# --- A. Happy path -----------------------------------------------------


def test_main_happy_path_returns_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_config = _FakeBootstrapConfig(mt5_symbol="BTCUSDt")
    monkeypatch.setattr(check_mt5_readonly, "_parse_args", lambda: _args(None))
    monkeypatch.setattr(check_mt5_readonly, "build_mt5_readonly_config_from_env", lambda: fake_config)

    constructed: list[tuple[object, str | None, object | None]] = []

    class _FakeClient:
        pass

    def _fake_mt5_client(*, path: str | None, credentials: object | None) -> _FakeClient:
        client = _FakeClient()
        constructed.append((client, path, credentials))
        return client

    monkeypatch.setattr(check_mt5_readonly, "MT5Client", _fake_mt5_client)

    smoke_calls: list[tuple[object, str]] = []

    def _fake_smoke(client: object, *, symbol: str) -> object:
        smoke_calls.append((client, symbol))
        return _canned_result(symbol, passed=True)

    monkeypatch.setattr(check_mt5_readonly, "run_mt5_readonly_smoke", _fake_smoke)

    exit_code = check_mt5_readonly.main()

    assert exit_code == 0
    assert len(constructed) == 1
    assert smoke_calls == [(constructed[0][0], "BTCUSDt")]


# --- B. Bootstrap configuration failure ---------------------------------


def test_main_bootstrap_failure_returns_one_and_never_touches_mt5(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(check_mt5_readonly, "_parse_args", lambda: _args(None))

    def _raise_bootstrap_error() -> object:
        raise check_mt5_readonly.BootstrapConfigurationError("Missing required environment variable: ADVISORY_MT5_SYMBOL")

    monkeypatch.setattr(check_mt5_readonly, "build_mt5_readonly_config_from_env", _raise_bootstrap_error)

    def _fail_if_client_constructed(*args: object, **kwargs: object) -> None:
        raise AssertionError("MT5Client must never be constructed when bootstrap config fails")

    monkeypatch.setattr(check_mt5_readonly, "MT5Client", _fail_if_client_constructed)

    def _fail_if_smoke_called(*args: object, **kwargs: object) -> None:
        raise AssertionError("run_mt5_readonly_smoke must never be called when bootstrap config fails")

    monkeypatch.setattr(check_mt5_readonly, "run_mt5_readonly_smoke", _fail_if_smoke_called)

    exit_code = check_mt5_readonly.main()

    assert exit_code == 1


# --- C. Unexpected runtime exception -------------------------------------


def test_main_unexpected_exception_returns_one_and_does_not_propagate(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_config = _FakeBootstrapConfig(mt5_symbol="BTCUSDt")
    monkeypatch.setattr(check_mt5_readonly, "_parse_args", lambda: _args(None))
    monkeypatch.setattr(check_mt5_readonly, "build_mt5_readonly_config_from_env", lambda: fake_config)
    monkeypatch.setattr(check_mt5_readonly, "MT5Client", lambda *, path, credentials: object())

    def _raise_unexpected(client: object, *, symbol: str) -> object:
        raise RuntimeError("boom")

    monkeypatch.setattr(check_mt5_readonly, "run_mt5_readonly_smoke", _raise_unexpected)

    exit_code = check_mt5_readonly.main()  # must not raise - the exception must not escape main()

    assert exit_code == 1


# --- D. --symbol precedence ----------------------------------------------


def test_main_cli_symbol_overrides_configured_symbol(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_config = _FakeBootstrapConfig(mt5_symbol="EURUSD")
    monkeypatch.setattr(check_mt5_readonly, "_parse_args", lambda: _args("BTCUSDt"))
    monkeypatch.setattr(check_mt5_readonly, "build_mt5_readonly_config_from_env", lambda: fake_config)
    monkeypatch.setattr(check_mt5_readonly, "MT5Client", lambda *, path, credentials: object())

    used_symbols: list[str] = []

    def _fake_smoke(client: object, *, symbol: str) -> object:
        used_symbols.append(symbol)
        return _canned_result(symbol, passed=True)

    monkeypatch.setattr(check_mt5_readonly, "run_mt5_readonly_smoke", _fake_smoke)

    exit_code = check_mt5_readonly.main()

    assert exit_code == 0
    assert used_symbols == ["BTCUSDt"]  # CLI override wins over the configured "EURUSD"


# --- E. Default symbol -----------------------------------------------------


def test_main_uses_configured_symbol_when_no_cli_override(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_config = _FakeBootstrapConfig(mt5_symbol="EURUSD")
    monkeypatch.setattr(check_mt5_readonly, "_parse_args", lambda: _args(None))
    monkeypatch.setattr(check_mt5_readonly, "build_mt5_readonly_config_from_env", lambda: fake_config)
    monkeypatch.setattr(check_mt5_readonly, "MT5Client", lambda *, path, credentials: object())

    used_symbols: list[str] = []

    def _fake_smoke(client: object, *, symbol: str) -> object:
        used_symbols.append(symbol)
        return _canned_result(symbol, passed=True)

    monkeypatch.setattr(check_mt5_readonly, "run_mt5_readonly_smoke", _fake_smoke)

    exit_code = check_mt5_readonly.main()

    assert exit_code == 0
    assert used_symbols == ["EURUSD"]  # no --symbol override: falls back to config.mt5_symbol
