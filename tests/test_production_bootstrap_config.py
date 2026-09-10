"""``app.bootstrap.production`` tests: minimal required env builds a valid
``ProductionAdvisoryConfig``, every documented default/failure path, and the
module's own hygiene (no execution-primitive method call, no secret in any
error message)."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from app.bootstrap.production import (
    BootstrapConfigurationError,
    build_production_advisory_config_from_env,
    build_production_advisory_service,
)
from app.core.enums.instrument import ContractType
from app.core.enums.market import MarketType

_MINIMAL_ENV = {
    "ADVISORY_SYMBOL": "EURUSD",
    "ADVISORY_CONTRACT_TYPE": "PERPETUAL",
    "ADVISORY_MARKET": "FX",
    "MT5_ROLLOVER_TIMEZONE": "UTC",
    "CALENDAR_BRIDGE_PATH": "C:/calendar/bridge.json",
    "CALENDAR_SERVER_TIMEZONE": "UTC",
}


def _set_minimal_env(monkeypatch: pytest.MonkeyPatch, **overrides: str | None) -> None:
    for name in (
        "ADVISORY_SYMBOL",
        "ADVISORY_CONTRACT_TYPE",
        "ADVISORY_MARKET",
        "MT5_ROLLOVER_TIMEZONE",
        "CALENDAR_BRIDGE_PATH",
        "CALENDAR_SERVER_TIMEZONE",
        "MT5_PATH",
        "MT5_LOGIN",
        "MT5_PASSWORD",
        "MT5_SERVER",
        "ADVISORY_ROLLOVER_STATE_PATH",
        "ADVISORY_TRACKING_DIR",
        "ADVISORY_PROVENANCE_DIR",
        "LLM_ENABLED",
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
        "OPENAI_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)
    for name, value in _MINIMAL_ENV.items():
        monkeypatch.setenv(name, value)
    for name, value in overrides.items():
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)


def test_minimal_required_env_builds_valid_config(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_minimal_env(monkeypatch)
    config = build_production_advisory_config_from_env()
    assert config.symbol == "EURUSD"
    assert config.contract_type is ContractType.PERPETUAL
    assert config.market is MarketType.FX
    assert config.rollover_policy.rollover_timezone == "UTC"
    assert config.calendar_server_timezone.server_timezone == "UTC"
    assert config.mt5_credentials is None
    assert config.llm_enabled is False
    assert config.llm_config is None
    assert config.base_asset is None
    assert config.network is None
    assert config.currency_exposures == ()


def test_path_defaults_exact(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_minimal_env(monkeypatch)
    config = build_production_advisory_config_from_env()
    assert config.rollover_state_path == Path("./data/rollover_state.json")
    assert config.tracking_directory == Path("./data/tracking")
    assert config.provenance_directory == Path("./data/provenance")


def test_path_overrides_respected(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_minimal_env(
        monkeypatch,
        ADVISORY_ROLLOVER_STATE_PATH="C:/custom/rollover.json",
        ADVISORY_TRACKING_DIR="C:/custom/tracking",
        ADVISORY_PROVENANCE_DIR="C:/custom/provenance",
    )
    config = build_production_advisory_config_from_env()
    assert config.rollover_state_path == Path("C:/custom/rollover.json")
    assert config.tracking_directory == Path("C:/custom/tracking")
    assert config.provenance_directory == Path("C:/custom/provenance")


def test_existing_domain_defaults_used_not_respecified(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config.trading_cycle import TradingCycleConfig
    from app.production_advisory.config import CALENDAR_STALENESS_THRESHOLD_DEFAULT

    _set_minimal_env(monkeypatch)
    config = build_production_advisory_config_from_env()
    assert config.trading_cycle_config == TradingCycleConfig()
    assert config.calendar_staleness_threshold == CALENDAR_STALENESS_THRESHOLD_DEFAULT
    assert config.event_symbol_scope_config.overrides == ()
    assert config.locked_override is False


def test_optional_mt5_path(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_minimal_env(monkeypatch, MT5_PATH="C:/terminal64.exe")
    config = build_production_advisory_config_from_env()
    assert config.mt5_path == "C:/terminal64.exe"


# --- MT5 credentials ---------------------------------------------------


def test_no_mt5_credentials_env_yields_none(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_minimal_env(monkeypatch)
    config = build_production_advisory_config_from_env()
    assert config.mt5_credentials is None


def test_all_mt5_credentials_present_builds_valid_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_minimal_env(monkeypatch, MT5_LOGIN="12345", MT5_PASSWORD="hunter2", MT5_SERVER="Broker-Live")
    config = build_production_advisory_config_from_env()
    assert config.mt5_credentials is not None
    assert config.mt5_credentials.login == 12345
    assert config.mt5_credentials.server == "Broker-Live"
    assert config.mt5_credentials.password.get_secret_value() == "hunter2"


def test_partial_mt5_credentials_fails_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_minimal_env(monkeypatch, MT5_LOGIN="12345")
    with pytest.raises(BootstrapConfigurationError) as exc_info:
        build_production_advisory_config_from_env()
    message = str(exc_info.value)
    assert "MT5_PASSWORD" in message
    assert "MT5_SERVER" in message


def test_invalid_mt5_login_fails_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_minimal_env(monkeypatch, MT5_LOGIN="not-a-number", MT5_PASSWORD="hunter2", MT5_SERVER="Broker-Live")
    with pytest.raises(BootstrapConfigurationError, match="MT5_LOGIN"):
        build_production_advisory_config_from_env()


def test_mt5_credentials_password_never_appears_in_error_output(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_minimal_env(monkeypatch, MT5_LOGIN="not-a-number", MT5_PASSWORD="super-secret-password", MT5_SERVER="Broker-Live")
    with pytest.raises(BootstrapConfigurationError) as exc_info:
        build_production_advisory_config_from_env()
    assert "super-secret-password" not in str(exc_info.value)
    assert "super-secret-password" not in repr(exc_info.value)


def test_valid_mt5_credentials_secret_never_appears_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_minimal_env(monkeypatch, MT5_LOGIN="12345", MT5_PASSWORD="super-secret-password", MT5_SERVER="Broker-Live")
    config = build_production_advisory_config_from_env()
    assert "super-secret-password" not in repr(config.mt5_credentials)
    assert "super-secret-password" not in str(config.mt5_credentials)


# --- LLM ---------------------------------------------------------------


def test_llm_disabled_never_requires_openai_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_minimal_env(monkeypatch, LLM_ENABLED="false")
    config = build_production_advisory_config_from_env()
    assert config.llm_enabled is False
    assert config.llm_config is None


def test_llm_enabled_requires_api_key_and_model(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_minimal_env(monkeypatch, LLM_ENABLED="true")
    with pytest.raises(BootstrapConfigurationError, match="OPENAI_API_KEY"):
        build_production_advisory_config_from_env()


def test_llm_enabled_with_full_config_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_minimal_env(monkeypatch, LLM_ENABLED="true", OPENAI_API_KEY="sk-fake-key", OPENAI_MODEL="gpt-5")
    config = build_production_advisory_config_from_env()
    assert config.llm_enabled is True
    assert config.llm_config is not None
    assert config.llm_config.model == "gpt-5"
    assert config.llm_config.api_key.get_secret_value() == "sk-fake-key"
    assert config.llm_config.timeout_seconds == 30.0  # this module's own default


def test_llm_api_key_never_appears_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_minimal_env(monkeypatch, LLM_ENABLED="true", OPENAI_API_KEY="sk-super-secret-key", OPENAI_MODEL="gpt-5")
    config = build_production_advisory_config_from_env()
    assert "sk-super-secret-key" not in repr(config.llm_config)
    assert "sk-super-secret-key" not in str(config.llm_config)


def test_invalid_llm_enabled_value_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_minimal_env(monkeypatch, LLM_ENABLED="maybe")
    with pytest.raises(BootstrapConfigurationError, match="LLM_ENABLED"):
        build_production_advisory_config_from_env()


# --- enum parsing --------------------------------------------------------


def test_invalid_contract_type_fails_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_minimal_env(monkeypatch, ADVISORY_CONTRACT_TYPE="BOGUS")
    with pytest.raises(BootstrapConfigurationError, match="ADVISORY_CONTRACT_TYPE"):
        build_production_advisory_config_from_env()


def test_invalid_market_fails_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_minimal_env(monkeypatch, ADVISORY_MARKET="BOGUS")
    with pytest.raises(BootstrapConfigurationError, match="ADVISORY_MARKET"):
        build_production_advisory_config_from_env()


def test_missing_required_var_message_names_the_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_minimal_env(monkeypatch, ADVISORY_SYMBOL=None)
    with pytest.raises(BootstrapConfigurationError, match="ADVISORY_SYMBOL"):
        build_production_advisory_config_from_env()


# --- service construction / hygiene ----------------------------------------


def test_build_production_advisory_service_never_calls_lifecycle_methods() -> None:
    """AST-based: this module must never call ``.startup(``/``.shutdown(``/
    ``.run_cycle(`` on anything it constructs - lifecycle ownership belongs
    exclusively to the caller."""
    import app.bootstrap.production as production_module

    tree = ast.parse(inspect.getsource(production_module))
    forbidden_calls = {"startup", "shutdown", "run_cycle"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in forbidden_calls, f"unexpected {node.func.attr}() call in app.bootstrap.production"


_FORBIDDEN_EXECUTION_IMPORTS = {
    "MT5Client",
    "BinanceRestClient",
    "OpenAIExplanationClient",
    "Judge",
    "RiskGate",
    "PortfolioSupervisor",
    "SessionGate",
    "SetupConstruction",
    "run_runtime_cycle",
}


def test_bootstrap_never_imports_execution_primitives_directly() -> None:
    import app.bootstrap.production as production_module

    tree = ast.parse(inspect.getsource(production_module))
    imported_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported_names.update(alias.asname or alias.name for alias in node.names)
        if isinstance(node, ast.Import):
            imported_names.update(alias.asname or alias.name for alias in node.names)
    assert imported_names.isdisjoint(_FORBIDDEN_EXECUTION_IMPORTS)


def test_build_production_advisory_service_builds_without_calling_provider_methods(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only proves construction succeeds and returns the right type - no
    MT5/Binance/OpenAI method is ever invoked by mere construction (both
    ``ProductionAdvisoryComposer.__init__`` and this module's own functions
    are pure object-graph assembly)."""
    from app.application.advisory_service import ApplicationAdvisoryService

    _set_minimal_env(monkeypatch)
    service = build_production_advisory_service()
    assert isinstance(service, ApplicationAdvisoryService)
