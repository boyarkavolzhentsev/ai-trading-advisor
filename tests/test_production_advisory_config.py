"""``ProductionAdvisoryConfig`` tests (Stage 0D Production Advisory
Composition)."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config.high_impact_event_bridge import HighImpactEventCalendarTimezoneConfig
from app.llm.openai_client import OpenAIExplanationClientConfig
from app.production_advisory.config import CALENDAR_STALENESS_THRESHOLD_DEFAULT, ProductionAdvisoryConfig, SymbolMapping
from tests.production_advisory_support import build_config


def test_single_authoritative_symbol_mapping_is_required() -> None:
    """Corrective design closure ("PROVIDER SYMBOL SPLIT + PRICE-BASIS
    RECONCILIATION"): one fixed SymbolMapping, never a bare ambiguous
    ``symbol`` string, is the sole authoritative instrument identity."""
    assert ProductionAdvisoryConfig.model_fields["symbol_mapping"].is_required()
    mapping = SymbolMapping(logical_symbol="BTC", binance_symbol="BTCUSDT", mt5_symbol="BTCUSDt")
    config = build_config(symbol_mapping=mapping)
    assert config.symbol_mapping.logical_symbol == "BTC"
    assert config.symbol_mapping.binance_symbol == "BTCUSDT"
    assert config.symbol_mapping.mt5_symbol == "BTCUSDt"


def test_max_price_basis_divergence_percent_is_required() -> None:
    assert ProductionAdvisoryConfig.model_fields["max_price_basis_divergence_percent"].is_required()


def test_calendar_staleness_threshold_defaults_to_fifteen_minutes() -> None:
    config = build_config()
    assert config.calendar_staleness_threshold == timedelta(minutes=15)
    assert CALENDAR_STALENESS_THRESHOLD_DEFAULT == timedelta(minutes=15)


def test_nested_configs_are_referenced_not_duplicated() -> None:
    tz = HighImpactEventCalendarTimezoneConfig(server_timezone="Europe/Nicosia")
    config = build_config(calendar_server_timezone=tz)
    assert config.calendar_server_timezone is tz


def test_invalid_timezone_rejected_by_existing_config_validator() -> None:
    with pytest.raises(ValidationError, match="unknown server_timezone"):
        HighImpactEventCalendarTimezoneConfig(server_timezone="Not/AZone")


def test_absent_calendar_path_is_a_valid_config_value() -> None:
    """Path existence is never a construction-time requirement - a
    calendar bridge file that does not exist yet is a normal, expected V1
    state (see the approved startup-semantics closure)."""
    config = build_config(calendar_bridge_path=Path("this/path/does/not/exist.json"))
    assert not config.calendar_bridge_path.exists()


def test_base_asset_and_network_must_both_be_supplied_or_both_omitted() -> None:
    with pytest.raises(ValidationError, match="base_asset and network"):
        build_config(base_asset="BTC")


def test_on_chain_pair_together_is_accepted() -> None:
    config = build_config(base_asset="BTC", network="bitcoin")
    assert config.base_asset == "BTC"
    assert config.network == "bitcoin"


def test_llm_config_required_when_enabled() -> None:
    with pytest.raises(ValidationError, match="llm_config is required"):
        build_config(llm_enabled=True)


def test_llm_disabled_by_default_and_config_optional() -> None:
    config = build_config()
    assert config.llm_enabled is False
    assert config.llm_config is None


def test_llm_enabled_with_config_accepted() -> None:
    llm_config = OpenAIExplanationClientConfig(api_key="secret", model="gpt-x", timeout_seconds=5.0)
    config = build_config(llm_enabled=True, llm_config=llm_config)
    assert config.llm_config is llm_config


def test_config_is_frozen() -> None:
    config = build_config()
    with pytest.raises(ValidationError):
        config.max_price_basis_divergence_percent = 999  # type: ignore[misc]
