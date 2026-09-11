"""Stage 0D Production Advisory Composition configuration.

The smallest immutable config set for one production advisory process: one
fixed, operator-configured V1 symbol/contract-type pair (the single
authoritative source ``ProductionAdvisoryComposer`` builds every downstream
``FlowRealtimeBootstrapConfig``/``TechnicalProductionConfig``/
``MarketEvaluationContext`` from - never an independently-declared copy),
plus every other already-approved nested configuration this composition
layer wires together, referenced by reference - never duplicated - from its
existing owner.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Final, Self

from pydantic import model_validator

from app.core.config.high_impact_event_bridge import HighImpactEventCalendarTimezoneConfig
from app.core.config.mt5_rollover import MT5RolloverPolicyConfig
from app.core.config.trading_cycle import TradingCycleConfig
from app.core.enums.instrument import ContractType
from app.core.enums.market import MarketType
from app.core.models.base import DomainModel, Percent, Symbol
from app.core.models.economic_event import CurrencyCode
from app.core.models.high_impact_event import HighImpactEventSymbolScopeConfig
from app.core.models.instrument import Asset
from app.core.models.mt5_runtime import MT5Credentials
from app.llm.openai_client import OpenAIExplanationClientConfig

CALENDAR_STALENESS_THRESHOLD_DEFAULT: Final[timedelta] = timedelta(minutes=15)
"""Approved V1 default (Calendar Bridge staleness-target closure): 5-minute
producer cadence, one missed refresh tolerated, sustained outage observable
soon enough to matter."""


class SymbolMapping(DomainModel):
    """One fixed instrument's three distinct, never-interchangeable
    identities (corrective design closure, "PROVIDER SYMBOL SPLIT + PRICE-
    BASIS RECONCILIATION"): provider-native symbol strings must never be
    silently treated as interchangeable.

    ``logical_symbol`` is operator-facing only - fed to no provider, no
    algorithm, no persistence key. ``binance_symbol`` is the only symbol
    Flow/Technical/``MarketEvaluationContext`` ever see. ``mt5_symbol`` is
    the only symbol MT5 ``symbol_facts``/the netting guard/Setup
    Construction's broker-facing identity/tracking/Stage 10E matching ever
    see. No registry, no multi-instrument lookup: exactly one fixed mapping
    per process, mirroring ``ProductionAdvisoryConfig``'s own existing
    "one fixed symbol per process" design.
    """

    logical_symbol: Symbol
    binance_symbol: Symbol
    mt5_symbol: Symbol


class ProductionAdvisoryConfig(DomainModel):
    """One process's complete, immutable production advisory configuration.

    ``base_asset``/``network`` mirror ``MarketEvaluationContext``'s own
    "both supplied or both omitted" invariant - re-validated here too so a
    malformed config is rejected at construction time, not deferred to the
    first cycle that builds a context from it. ``llm_config`` is required
    exactly when ``llm_enabled`` is true - no silent default construction of
    a real provider client from partial/absent configuration.
    """

    symbol_mapping: SymbolMapping
    contract_type: ContractType
    market: MarketType
    base_asset: Asset | None = None
    network: str | None = None
    currency_exposures: tuple[CurrencyCode, ...] = ()

    max_price_basis_divergence_percent: Percent
    """Required, no default (corrective design closure, "PROVIDER SYMBOL
    SPLIT + PRICE-BASIS RECONCILIATION"): the maximum tolerated divergence
    between the MT5 entry price and the Binance M15 reference price before
    Setup Construction refuses to translate a structural stop onto MT5's
    price axis (``SetupBlockReason.PRICE_BASIS_DIVERGENCE``). A wrong
    default would silently mask a real, evolving venue basis - mirrors
    ``MT5RolloverPolicyConfig.rollover_timezone``'s own "no default" rationale.
    This is deliberately NOT chosen by this codebase: it must be set by the
    operator from observed BTCUSDT/BTCUSDt basis behavior before any
    ACTIONABLE-capable live run."""

    rollover_policy: MT5RolloverPolicyConfig
    trading_cycle_config: TradingCycleConfig = TradingCycleConfig()

    mt5_path: str | None = None
    mt5_credentials: MT5Credentials | None = None

    rollover_state_path: Path
    tracking_directory: Path
    provenance_directory: Path

    calendar_bridge_path: Path
    calendar_server_timezone: HighImpactEventCalendarTimezoneConfig
    calendar_staleness_threshold: timedelta = CALENDAR_STALENESS_THRESHOLD_DEFAULT
    event_symbol_scope_config: HighImpactEventSymbolScopeConfig = HighImpactEventSymbolScopeConfig()

    llm_enabled: bool = False
    llm_config: OpenAIExplanationClientConfig | None = None

    locked_override: bool = False

    @model_validator(mode="after")
    def _validate_on_chain_pair(self) -> Self:
        if (self.base_asset is None) != (self.network is None):
            raise ValueError("base_asset and network must both be supplied or both omitted")
        return self

    @model_validator(mode="after")
    def _validate_llm_config_present_when_enabled(self) -> Self:
        if self.llm_enabled and self.llm_config is None:
            raise ValueError("llm_config is required when llm_enabled is true")
        return self


__all__ = ["CALENDAR_STALENESS_THRESHOLD_DEFAULT", "ProductionAdvisoryConfig", "SymbolMapping"]
