"""Production object-graph construction from environment variables.

The ONE module allowed to import ``ProductionAdvisoryConfig``/
``ProductionAdvisoryComposer``/``MT5Credentials``/
``OpenAIExplanationClientConfig`` and construct them - transport code
(``app.api.*``) never does (see the approved FastAPI design closure,
"5. COMPOSITION ROOT - RESOLVE"). This module only constructs objects: it
never calls ``.startup()``/``.shutdown()``/``.run_cycle()`` on anything it
builds, never reads MT5/Binance/OpenAI method-level state, and never
reimplements Judge/Risk/Portfolio/Session/Setup logic - those all remain
``ProductionAdvisoryComposer``'s own exclusive responsibility, one layer
below.

Every parsing helper below is deliberately small and explicit (no settings
framework, no ``pydantic-settings``, no ``.env`` loader) - mirrors this
repository's own existing convention (``OpenAIExplanationClientConfig``'s own
docstring: "No field reads the environment... every value here is an
explicit, reviewable choice the caller supplies") one layer up, at the one
boundary that legitimately must read ``os.environ``.

Every error raised here is a sanitized ``BootstrapConfigurationError``
naming only the environment *variable*, never its value - a missing/invalid
``MT5_PASSWORD``/``OPENAI_API_KEY`` is reported by name only, never by
content, and no secret is ever logged (see ``_build_mt5_credentials``/
``_build_llm_config``, which wrap raw secret strings in ``SecretStr``
immediately, at the single construction call site, and never hold them as a
plain ``str`` beyond that line).
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import SecretStr, ValidationError

from app.application.advisory_service import ApplicationAdvisoryService
from app.application.cycle_receipt import CycleReceiptPersistence
from app.core.config.high_impact_event_bridge import HighImpactEventCalendarTimezoneConfig
from app.core.config.mt5_rollover import MT5RolloverPolicyConfig
from app.core.enums.instrument import ContractType
from app.core.enums.market import MarketType
from app.core.models.mt5_runtime import MT5Credentials
from app.llm.openai_client import OpenAIExplanationClientConfig
from app.production_advisory.composer import ProductionAdvisoryComposer
from app.production_advisory.config import ProductionAdvisoryConfig

_DEFAULT_ROLLOVER_STATE_PATH = "./data/rollover_state.json"
_DEFAULT_TRACKING_DIR = "./data/tracking"
_DEFAULT_PROVENANCE_DIR = "./data/provenance"
_DEFAULT_CYCLE_RECEIPT_DIR = "./data/cycle_receipts"
"""Deliberately a sibling of tracking/provenance, never nested inside either:
both of those directories are globbed by trade_id (``MT5RecommendationPersistence.
list_trade_ids()``/``MT5RecommendationProvenancePersistence.list_trade_ids()``)
and feed real Stage 10E tracking-advancement logic every cycle - a
logical_cycle_id-keyed receipt file must never be placed where that scan
could ever see it (corrective design closure, "CYCLE-LEVEL IDEMPOTENCY")."""
_DEFAULT_OPENAI_TIMEOUT_SECONDS = 30.0
"""This bootstrap module's own operational default - ``OpenAIExplanationClientConfig.
timeout_seconds`` itself has no domain-level default (a required field), so a
value must be supplied somewhere; this is that one place, not a claim about
an existing approved domain default."""

_MT5_CREDENTIAL_VARS = ("MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER")
_TRUE_VALUES = frozenset({"true", "1"})
_FALSE_VALUES = frozenset({"false", "0"})


class BootstrapConfigurationError(Exception):
    """Raised when the production environment cannot be assembled into a
    valid ``ProductionAdvisoryConfig``. Every message names only an
    environment variable's *name*, never its value - never a secret, never a
    full ``os.environ`` dump."""


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise BootstrapConfigurationError(f"Missing required environment variable: {name}")
    return value


def _optional_env(name: str) -> str | None:
    value = os.environ.get(name)
    return value if value else None


def _parse_bool_env(name: str, *, default: bool) -> bool:
    raw = os.environ.get(name)
    if not raw:
        return default
    normalized = raw.strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise BootstrapConfigurationError(f"Invalid value for environment variable: {name} (expected one of true/false/1/0)")


def _parse_enum_env(name: str, enum_cls: type) -> object:
    raw = _require_env(name)
    try:
        return enum_cls(raw)
    except ValueError:
        valid = ", ".join(member.value for member in enum_cls)
        raise BootstrapConfigurationError(f"Invalid value for environment variable: {name} (expected one of: {valid})") from None


def _parse_positive_int_env(name: str) -> int:
    raw = _require_env(name)
    try:
        value = int(raw)
    except ValueError:
        raise BootstrapConfigurationError(f"Invalid value for environment variable: {name} (expected a positive integer)") from None
    if value <= 0:
        raise BootstrapConfigurationError(f"Invalid value for environment variable: {name} (expected a positive integer)")
    return value


def _parse_positive_float_env(name: str, *, default: float) -> float:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        raise BootstrapConfigurationError(f"Invalid value for environment variable: {name} (expected a positive number)") from None
    if value <= 0:
        raise BootstrapConfigurationError(f"Invalid value for environment variable: {name} (expected a positive number)")
    return value


def _parse_path_env(name: str, *, default: str) -> Path:
    raw = os.environ.get(name)
    return Path(raw) if raw else Path(default)


def _build_mt5_credentials() -> MT5Credentials | None:
    """All three of ``MT5_LOGIN``/``MT5_PASSWORD``/``MT5_SERVER`` present ->
    explicit headless-login credentials. None present -> ``None`` (use
    whatever account the local terminal is already authenticated as - the
    preferred V1 mode, per ``MT5Credentials``'s own docstring). Any other
    combination is a sanitized configuration failure - partial credentials
    are never silently accepted."""
    raw_values = {name: _optional_env(name) for name in _MT5_CREDENTIAL_VARS}
    present = [name for name, value in raw_values.items() if value is not None]
    if not present:
        return None

    missing = [name for name in _MT5_CREDENTIAL_VARS if raw_values[name] is None]
    if missing:
        raise BootstrapConfigurationError(
            "Partial MT5 credentials: MT5_LOGIN, MT5_PASSWORD, and MT5_SERVER must all be present "
            f"together, or all omitted. Missing: {', '.join(missing)}"
        )

    login_raw = raw_values["MT5_LOGIN"]
    assert login_raw is not None  # guaranteed: "MT5_LOGIN" not in missing
    try:
        login = int(login_raw)
    except ValueError:
        raise BootstrapConfigurationError("Invalid value for environment variable: MT5_LOGIN (expected a positive integer)") from None
    if login <= 0:
        raise BootstrapConfigurationError("Invalid value for environment variable: MT5_LOGIN (expected a positive integer)")

    password = raw_values["MT5_PASSWORD"]
    server = raw_values["MT5_SERVER"]
    assert password is not None and server is not None  # guaranteed: neither is in missing
    return MT5Credentials(login=login, password=SecretStr(password), server=server)


def _build_llm_config(*, llm_enabled: bool) -> OpenAIExplanationClientConfig | None:
    """``OPENAI_API_KEY``/``OPENAI_MODEL`` are read - and required - only
    when ``llm_enabled`` is ``True``. When disabled, neither is read at all."""
    if not llm_enabled:
        return None
    api_key = _require_env("OPENAI_API_KEY")
    model = _require_env("OPENAI_MODEL")
    timeout_seconds = _parse_positive_float_env("OPENAI_TIMEOUT_SECONDS", default=_DEFAULT_OPENAI_TIMEOUT_SECONDS)
    return OpenAIExplanationClientConfig(api_key=SecretStr(api_key), model=model, timeout_seconds=timeout_seconds)


def build_production_advisory_config_from_env() -> ProductionAdvisoryConfig:
    """Construct the one, fixed-symbol ``ProductionAdvisoryConfig`` this
    process runs for, from explicit named environment variables only - no
    settings framework, no ``.env`` file loading. Never creates a directory
    or touches the filesystem itself (paths are only parsed, never created -
    that remains ``ProductionAdvisoryComposer``'s own concern if it needs
    one)."""
    symbol = _require_env("ADVISORY_SYMBOL")
    contract_type = _parse_enum_env("ADVISORY_CONTRACT_TYPE", ContractType)
    market = _parse_enum_env("ADVISORY_MARKET", MarketType)
    rollover_timezone = _require_env("MT5_ROLLOVER_TIMEZONE")
    calendar_bridge_path = Path(_require_env("CALENDAR_BRIDGE_PATH"))
    calendar_server_timezone_value = _require_env("CALENDAR_SERVER_TIMEZONE")

    mt5_path = _optional_env("MT5_PATH")
    mt5_credentials = _build_mt5_credentials()

    rollover_state_path = _parse_path_env("ADVISORY_ROLLOVER_STATE_PATH", default=_DEFAULT_ROLLOVER_STATE_PATH)
    tracking_directory = _parse_path_env("ADVISORY_TRACKING_DIR", default=_DEFAULT_TRACKING_DIR)
    provenance_directory = _parse_path_env("ADVISORY_PROVENANCE_DIR", default=_DEFAULT_PROVENANCE_DIR)

    llm_enabled = _parse_bool_env("LLM_ENABLED", default=False)
    llm_config = _build_llm_config(llm_enabled=llm_enabled)

    try:
        return ProductionAdvisoryConfig(
            symbol=symbol,
            contract_type=contract_type,
            market=market,
            # base_asset/network/currency_exposures: omitted for V1 - the
            # model's own defaults (None/None/()) apply; no on-chain scope
            # env var is introduced (see the approved design closure, "23.
            # OPTIONAL ON-CHAIN FIELDS").
            rollover_policy=MT5RolloverPolicyConfig(rollover_timezone=rollover_timezone),
            # trading_cycle_config: omitted - ProductionAdvisoryConfig's own
            # field default (TradingCycleConfig()) is fully self-sufficient.
            mt5_path=mt5_path,
            mt5_credentials=mt5_credentials,
            rollover_state_path=rollover_state_path,
            tracking_directory=tracking_directory,
            provenance_directory=provenance_directory,
            calendar_bridge_path=calendar_bridge_path,
            calendar_server_timezone=HighImpactEventCalendarTimezoneConfig(server_timezone=calendar_server_timezone_value),
            # calendar_staleness_threshold/event_symbol_scope_config/
            # locked_override: omitted - each has its own approved domain
            # default (see the approved design closure, "24. EXISTING SAFE
            # CONFIG DEFAULTS").
            llm_enabled=llm_enabled,
            llm_config=llm_config,
        )
    except ValidationError as exc:
        # Never pass exc.errors()[*]["input"] through - only the field path
        # and pydantic's own message, never the raw value that failed
        # validation (which could, in principle, be a secret-adjacent field).
        details = "; ".join(f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}" for error in exc.errors())
        raise BootstrapConfigurationError(f"Invalid production configuration: {details}") from exc


def build_production_advisory_service() -> ApplicationAdvisoryService:
    """Construct one ``ProductionAdvisoryComposer`` from the environment and
    wrap it in one ``ApplicationAdvisoryService``, together with the one
    ``CycleReceiptPersistence`` that gives ``logical_cycle_id`` cycle-level
    idempotency (corrective design closure, "CYCLE-LEVEL IDEMPOTENCY") - the
    only real production ``ApplicationAdvisoryService`` construction site in
    this repository, so this is the one place that must never leave a real
    caller without it. Never calls ``.startup()``/``.run_cycle()``/
    ``.shutdown()`` - lifecycle ownership belongs to the caller (FastAPI
    ``lifespan``).

    ``ADVISORY_CYCLE_RECEIPT_DIR`` is deliberately parsed here, not inside
    ``build_production_advisory_config_from_env()``: it is an
    Application-layer concern (``ApplicationAdvisoryService`` is the sole
    owner of ``logical_cycle_id`` semantics - ``ProductionAdvisoryComposer``/
    ``ProductionAdvisoryConfig`` never see a ``logical_cycle_id`` at all), so
    it is never threaded through the unrelated, unchanged Stage0D/production
    market-and-provider configuration.
    """
    config = build_production_advisory_config_from_env()
    composer = ProductionAdvisoryComposer(config=config)
    cycle_receipt_directory = _parse_path_env("ADVISORY_CYCLE_RECEIPT_DIR", default=_DEFAULT_CYCLE_RECEIPT_DIR)
    cycle_receipt_persistence = CycleReceiptPersistence(cycle_receipt_directory)
    return ApplicationAdvisoryService(composer=composer, cycle_receipt_persistence=cycle_receipt_persistence)


__all__ = [
    "BootstrapConfigurationError",
    "build_production_advisory_config_from_env",
    "build_production_advisory_service",
]
