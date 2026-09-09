"""Stage 0D Production Advisory Composition.

The one process-level coordinator that wires every already-approved,
already-closed production/runtime seam together for exactly one fixed,
operator-configured V1 symbol: Flow realtime bootstrap (Stage 0A) +
Technical production composition (Stage 0B) + the MQL5 calendar bridge file
reader + the deterministic runtime-cycle orchestrator
(``run_runtime_cycle``) + the LLM explanation layer.

Owns every side effect this layer is approved to own: the one shared
``BinanceRestClient``, Flow's realtime start/stop lifecycle, the process-
local cycle lock, and the duplicate-cycle persistence preflight. Owns
NOTHING already owned by a closed module: it never calls
``MT5ClientProtocol.initialize``/``account_facts``/``positions``/
``history_deals``/``symbol_facts``/``shutdown`` directly -
``run_runtime_cycle`` remains the sole owner of every per-cycle MT5 read
(and of MT5 initialize/shutdown itself, which it already performs per call)
- never reproduces Judge/Risk/Portfolio/Session/Setup-Construction logic,
and never generates a ``trade_id`` or a business-logic wall-clock timestamp
of its own: both ``as_of`` and ``trade_ids`` are caller-supplied on every
``run_cycle`` call.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping
from typing import Literal

from app.core.enums.explanation import ExplanationProviderStatus
from app.core.enums.runtime_cycle import RuntimeCycleOutcome
from app.core.enums.strategy_router import StrategyFamily
from app.core.models.base import Timestamp
from app.core.models.market_evaluation_context import MarketEvaluationContext
from app.flow.realtime_bootstrap import FlowRealtimeBootstrap, FlowRealtimeBootstrapConfig
from app.high_impact_event_bridge.file_reader import read_high_impact_event_context
from app.llm.openai_client import OpenAIExplanationClient
from app.llm.protocols import ExplanationLLMClient
from app.market_data.providers.binance.client import BinanceRestClient
from app.market_data.providers.binance.futures.constants import BINANCE_FUTURES_BASE_URL, DEFAULT_TIMEOUT_SECONDS
from app.market_data.providers.binance.futures.provider import BinanceFuturesMarketDataProvider
from app.mt5.client import MT5Client
from app.mt5.persistence import MT5RolloverStatePersistence
from app.mt5.protocols import MT5ClientProtocol
from app.mt5.recommendation_persistence import MT5RecommendationPersistence
from app.mt5.recommendation_provenance_persistence import MT5RecommendationProvenancePersistence
from app.orchestration.explanation import (
    build_explanation_context,
    build_recommendation_cards,
    build_tracking_cards,
    explain_runtime_cycle,
    render_deterministic_fallback,
)
from app.orchestration.runtime_cycle import run_runtime_cycle
from app.production_advisory.config import ProductionAdvisoryConfig
from app.production_advisory.errors import ProductionAdvisoryDuplicateCycleError, ProductionAdvisoryLifecycleError
from app.production_advisory.lock import ProductionAdvisoryCycleLock
from app.production_advisory.result import ProductionAdvisoryCycleOutcome, ProductionAdvisoryCycleResult
from app.technical.production import TechnicalProductionComposer, TechnicalProductionConfig

_LifecycleState = Literal["NEW", "STARTED", "STOPPED"]


def _default_flow_bootstrap(config: ProductionAdvisoryConfig, rest_client: BinanceRestClient) -> FlowRealtimeBootstrap:
    return FlowRealtimeBootstrap(
        config=FlowRealtimeBootstrapConfig(symbol=config.symbol, contract_type=config.contract_type),
        rest_client=rest_client,
    )


def _default_technical_composer(
    config: ProductionAdvisoryConfig, rest_client: BinanceRestClient
) -> TechnicalProductionComposer:
    provider = BinanceFuturesMarketDataProvider(rest_client)
    return TechnicalProductionComposer(
        config=TechnicalProductionConfig(symbol=config.symbol, contract_type=config.contract_type),
        provider=provider,
    )


class ProductionAdvisoryComposer:
    """Owns Stage0D's long-lived production resources and exposes the one
    per-cycle entry point, ``run_cycle``.

    Every dependency is injectable for testing (no real network, no real
    MT5/OpenAI SDK) - each defaults to the real production component when
    omitted, mirroring ``FlowRealtimeBootstrap``'s own established
    injectable-with-real-defaults convention.
    """

    def __init__(
        self,
        *,
        config: ProductionAdvisoryConfig,
        flow_bootstrap: FlowRealtimeBootstrap | None = None,
        technical_composer: TechnicalProductionComposer | None = None,
        mt5_client: MT5ClientProtocol | None = None,
        rollover_persistence: MT5RolloverStatePersistence | None = None,
        tracking_persistence: MT5RecommendationPersistence | None = None,
        provenance_persistence: MT5RecommendationProvenancePersistence | None = None,
        llm_client: ExplanationLLMClient | None = None,
        rest_client: BinanceRestClient | None = None,
    ) -> None:
        self._config = config
        self._lock = ProductionAdvisoryCycleLock()
        self._lifecycle_state: _LifecycleState = "NEW"

        self._rest_client = (
            rest_client
            if rest_client is not None
            else BinanceRestClient(base_url=BINANCE_FUTURES_BASE_URL, timeout=DEFAULT_TIMEOUT_SECONDS)
        )
        self._owns_rest_client = rest_client is None

        self._flow_bootstrap = (
            flow_bootstrap if flow_bootstrap is not None else _default_flow_bootstrap(config, self._rest_client)
        )
        self._technical_composer = (
            technical_composer
            if technical_composer is not None
            else _default_technical_composer(config, self._rest_client)
        )

        self._mt5_client: MT5ClientProtocol = (
            mt5_client if mt5_client is not None else MT5Client(path=config.mt5_path, credentials=config.mt5_credentials)
        )

        self._rollover_persistence = (
            rollover_persistence if rollover_persistence is not None else MT5RolloverStatePersistence(config.rollover_state_path)
        )
        self._tracking_persistence = (
            tracking_persistence if tracking_persistence is not None else MT5RecommendationPersistence(config.tracking_directory)
        )
        self._provenance_persistence = (
            provenance_persistence
            if provenance_persistence is not None
            else MT5RecommendationProvenancePersistence(config.provenance_directory)
        )

        if llm_client is not None:
            self._llm_client: ExplanationLLMClient | None = llm_client
            self._llm_enabled = True
        elif config.llm_enabled:
            assert config.llm_config is not None  # enforced by ProductionAdvisoryConfig's own validator
            self._llm_client = OpenAIExplanationClient(config=config.llm_config)
            self._llm_enabled = True
        else:
            self._llm_client = None
            self._llm_enabled = False

    # --- lifecycle -----------------------------------------------------

    async def startup(self) -> None:
        """Starts Flow's realtime bootstrap only. Never initializes MT5 -
        ``run_runtime_cycle`` already owns MT5 initialize/shutdown per call
        (see its own docstring). Calendar path existence is never checked
        here - a missing file is a normal, expected, per-cycle-re-evaluated
        state (see ``run_cycle``'s calendar read), not a startup blocker.
        Timezone config validation already happened at
        ``ProductionAdvisoryConfig``/``HighImpactEventCalendarTimezoneConfig``
        construction time - there is nothing further to validate here.

        Idempotent from ``STARTED`` (a no-op, mirroring
        ``FlowRealtimeBootstrap.start()``'s own idempotence); raises
        ``ProductionAdvisoryLifecycleError`` from ``STOPPED`` - restarting a
        shut-down composer is never supported, per the smallest-lifecycle-
        guard closure. Construct a new ``ProductionAdvisoryComposer``
        instead.
        """
        if self._lifecycle_state == "STARTED":
            return
        if self._lifecycle_state == "STOPPED":
            raise ProductionAdvisoryLifecycleError("startup() cannot be called after shutdown() - construct a new ProductionAdvisoryComposer instead")
        await self._flow_bootstrap.start()
        self._lifecycle_state = "STARTED"

    async def shutdown(self) -> None:
        """Reverses ``startup()``. Stops Flow first (idempotent, tears down
        every Stage 0A task in dependency order), then closes the shared
        ``BinanceRestClient`` exactly once - only if this composer
        constructed it itself. ``FlowRealtimeBootstrap.stop()`` never
        closes it (it was injected, so ``_owns_rest_client`` is ``False``
        on the bootstrap's own side) - this is the single closer, never a
        double-close, and never closes a caller-injected client.

        Always idempotent, including from ``NEW`` (nothing was ever
        started, but the shared REST client this composer constructed at
        ``__init__`` is still closed for cleanliness) and from ``STOPPED``
        (a no-op) - shutdown never raises.
        """
        if self._lifecycle_state == "STOPPED":
            return
        await self._flow_bootstrap.stop()
        if self._owns_rest_client:
            self._rest_client.close()
        self._lifecycle_state = "STOPPED"

    # --- per-cycle entry point ------------------------------------------

    async def run_cycle(
        self,
        *,
        as_of: Timestamp,
        trade_ids: Mapping[StrategyFamily, str],
    ) -> ProductionAdvisoryCycleResult:
        """Run exactly one production advisory cycle.

        ``as_of`` and ``trade_ids`` are both caller-supplied on every call -
        this method never reads the wall clock for business logic and never
        generates a trade_id (no ``uuid``/``random``/``secrets`` anywhere in
        this class). The duplicate-cycle preflight and the entire cycle
        execute inside the same lock acquisition, so two concurrent calls
        with identical ``trade_ids`` can never both pass the preflight
        before either persists (see the approved retry/idempotency design
        closure).

        Raises ``ProductionAdvisoryLifecycleError`` unless the composer is
        currently ``STARTED`` (see ``startup()``/``shutdown()``) - never
        silently runs a cycle against a Flow bootstrap whose background
        tasks were never started (which would otherwise degrade forever
        with no data, indistinguishable from a genuine quiet market) or
        against resources shutdown() may already have closed.
        """
        if self._lifecycle_state != "STARTED":
            raise ProductionAdvisoryLifecycleError(
                f"run_cycle() requires a started composer (current state: {self._lifecycle_state}) - call startup() first"
            )
        self._validate_trade_id_coverage(trade_ids)

        async with self._lock:
            self._reject_if_duplicate_cycle(trade_ids)

            started_at = time.perf_counter()

            flow_result = self._flow_bootstrap.build_flow_result(as_of=as_of)

            technical_result = await asyncio.to_thread(self._technical_composer.build_technical_result, as_of=as_of)

            if technical_result.fetch_failures:
                # Approved V1 Technical safety policy: any current-cycle
                # fetch failure discards the entire Technical result for
                # this cycle rather than trusting retained-but-unprovably-
                # fresh Stage 3A history. Never a partial per-cell patch.
                technical = None
                m15_market_structure = None
            else:
                technical = technical_result.technical
                m15_market_structure = technical_result.m15_market_structure

            high_impact_event_context = read_high_impact_event_context(
                self._config.calendar_bridge_path,
                as_of=as_of,
                staleness_threshold=self._config.calendar_staleness_threshold,
                timezone_config=self._config.calendar_server_timezone,
            )

            context = MarketEvaluationContext(
                symbol=self._config.symbol,
                contract_type=self._config.contract_type,
                base_asset=self._config.base_asset,
                network=self._config.network,
                currency_exposures=self._config.currency_exposures,
            )

            runtime_cycle_result = run_runtime_cycle(
                client=self._mt5_client,
                as_of=as_of,
                rollover_policy=self._config.rollover_policy,
                rollover_persistence=self._rollover_persistence,
                tracking_persistence=self._tracking_persistence,
                provenance_persistence=self._provenance_persistence,
                trading_cycle_config=self._config.trading_cycle_config,
                market=self._config.market,
                trade_ids=trade_ids,
                context=context,
                flow=flow_result,
                technical=technical,
                external=None,
                m15_market_structure=m15_market_structure,
                locked_override=self._config.locked_override,
                high_impact_event_context=high_impact_event_context,
                high_impact_event_symbol_scope_config=self._config.event_symbol_scope_config,
            )

            if self._llm_enabled:
                assert self._llm_client is not None  # guaranteed by __init__ whenever _llm_enabled is True
                explanation_result = explain_runtime_cycle(result=runtime_cycle_result, llm_client=self._llm_client)
            else:
                # llm_enabled=False is a normal, expected operator
                # configuration, never an exceptional/failure condition -
                # calling the existing public deterministic-fallback seam
                # directly (never reproducing its logic) avoids using an
                # exception as ordinary control flow for what happens on
                # every single cycle while disabled. ExplanationProviderStatus
                # has no DISABLED member, so LLM_UNAVAILABLE remains the
                # closest existing label here - the separate
                # ProductionAdvisoryCycleResult.llm_enabled field is what
                # actually disambiguates "disabled" from "enabled but the
                # provider failed" for a future status/diagnostics consumer.
                explanation_result = render_deterministic_fallback(
                    context=build_explanation_context(runtime_cycle_result),
                    recommendation_cards=build_recommendation_cards(runtime_cycle_result),
                    tracking_cards=build_tracking_cards(runtime_cycle_result),
                    provider_status=ExplanationProviderStatus.LLM_UNAVAILABLE,
                )

            outcome = (
                ProductionAdvisoryCycleOutcome.SERVICE_UNAVAILABLE
                if runtime_cycle_result.outcome is RuntimeCycleOutcome.BLOCKED
                else ProductionAdvisoryCycleOutcome.READY
            )

            cycle_duration_seconds = time.perf_counter() - started_at
            # perf_counter is used for operational diagnostics only (cycle
            # duration reporting) - it never influences any trading/domain
            # decision and is never threaded into any pure module's as_of.

            return ProductionAdvisoryCycleResult(
                as_of=as_of,
                symbol=self._config.symbol,
                outcome=outcome,
                runtime_cycle_result=runtime_cycle_result,
                explanation_result=explanation_result,
                llm_enabled=self._llm_enabled,
                flow_health=self._flow_bootstrap.health(),
                technical_fetch_failures=technical_result.fetch_failures,
                cycle_duration_seconds=cycle_duration_seconds,
            )

    # --- preflight helpers -----------------------------------------------

    @staticmethod
    def _validate_trade_id_coverage(trade_ids: Mapping[StrategyFamily, str]) -> None:
        """Every ``StrategyFamily`` must have a supplied ``trade_id`` -
        which families end up actionable is only known after Stage 5-9 run,
        so under-supplying risks ``MissingTradeIdForActionableFamilyError``
        deep inside ``construct_final_recommendations`` (a caller-contract
        violation, not a business block) - checked upfront instead."""
        missing = set(StrategyFamily) - set(trade_ids.keys())
        if missing:
            raise ValueError(f"trade_ids missing entries for: {sorted(family.value for family in missing)}")

    def _reject_if_duplicate_cycle(self, trade_ids: Mapping[StrategyFamily, str]) -> None:
        """Reads only - no write of any kind. Checks EVERY supplied
        trade_id against BOTH persistence stores; a match anywhere other
        than ``"ABSENT"`` refuses the WHOLE cycle, never a partial subset,
        and is independent of ``AccountPositionMode``
        (NETTING/UNKNOWN/HEDGING all reach this same check identically -
        the existing NETTING-only issuance guard is never relied upon here).
        """
        colliding: list[str] = []
        for trade_id in trade_ids.values():
            tracking_status, _ = self._tracking_persistence.read(trade_id)
            provenance_status, _ = self._provenance_persistence.read(trade_id)
            if tracking_status != "ABSENT" or provenance_status != "ABSENT":
                colliding.append(trade_id)
        if colliding:
            raise ProductionAdvisoryDuplicateCycleError(tuple(colliding))


__all__ = ["ProductionAdvisoryComposer"]
