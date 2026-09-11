"""Stage 0D internal composition result - not an HTTP DTO.

Embeds every already-existing authoritative object whole
(``RuntimeCycleResult``/``ExplanationResult``) - never re-derives or
duplicates a nested field. The one new fact this layer contributes is
``outcome``: a narrow, provably-derived operational classification, kept
structurally separate from ``RuntimeCycleOutcome``/
``FinalRecommendationOutcome``/any trading-domain block reason.
"""

from __future__ import annotations

from enum import StrEnum

from app.core.models.base import DomainModel, Symbol, Timestamp
from app.core.models.explanation import ExplanationResult
from app.core.models.runtime_cycle import RuntimeCycleResult
from app.flow.realtime_bootstrap import FlowRealtimeBootstrapHealth
from app.technical.production import TechnicalFetchFailure


class ProductionAdvisoryCycleOutcome(StrEnum):
    """Coarse, composition-level classification of one Stage 0D cycle -
    never a trading-domain verdict.

    ``SERVICE_UNAVAILABLE`` is derived exclusively from
    ``RuntimeCycleResult.outcome is RuntimeCycleOutcome.BLOCKED`` - that
    member's own docstring proves it means "MT5 connectivity itself was
    unavailable this cycle" and nothing else (``app.core.enums.
    runtime_cycle.RuntimeCycleOutcome``), so this mapping is mechanically
    safe, never a guess. Every other ``RuntimeCycleOutcome``
    (``READY``/``PARTIAL_DEGRADED``) maps to ``READY`` here - a degraded-
    but-completed cycle is still a valid, usable advisory result, per the
    approved failure-taxonomy closure.

    ``ALREADY_PROCESSED`` deliberately has no member here: a duplicate
    cycle never reaches the point of constructing a
    ``ProductionAdvisoryCycleResult`` at all - it is reported exclusively
    via ``ProductionAdvisoryDuplicateCycleError`` (``app.production_advisory.
    errors``), kept structurally distinct from this outcome vocabulary.
    """

    READY = "READY"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"


class ProductionAdvisoryCycleResult(DomainModel):
    """Stage 0D's complete, typed, single-cycle deliverable.

    ``runtime_cycle_result`` remains the sole deterministic trading
    authority; ``explanation_result`` remains non-authoritative narrative-
    only output. ``flow_health``/``technical_fetch_failures``/
    ``cycle_duration_seconds``/``llm_enabled`` are operational diagnostics
    only - never consulted by, and never influencing, any domain decision.

    ``llm_enabled`` disambiguates, for a future ``/status``/monitoring
    consumer, "the operator intentionally disabled the LLM" (``False`` -
    ``explanation_result.provider_status`` is ``LLM_UNAVAILABLE`` only
    because that is the closest existing label, never because anything is
    actually failing) from "the LLM was enabled but the provider itself
    failed this cycle" (``True`` alongside ``provider_status ==
    LLM_UNAVAILABLE``) - a distinction ``ExplanationProviderStatus`` itself
    has no member for (see the approved LLM-disabled-semantics corrective
    review), resolved here at the Stage0D layer only, without modifying
    the closed explanation domain.

    ``symbol``/``market_data_symbol`` (corrective design closure, "PROVIDER
    SYMBOL SPLIT + PRICE-BASIS RECONCILIATION"): ``symbol`` is the
    operator-facing logical instrument identifier (``SymbolMapping.
    logical_symbol``), fed to no provider; ``market_data_symbol`` is the
    Binance symbol (``SymbolMapping.binance_symbol``) the analytical
    evidence actually came from. Neither is the MT5 broker-facing symbol -
    that lives only on each issued ``FinalRecommendation``/
    ``RecommendationDTO``, since a cycle with zero recommendations has no
    single broker symbol to report at this level.
    """

    as_of: Timestamp
    symbol: Symbol
    market_data_symbol: Symbol
    outcome: ProductionAdvisoryCycleOutcome
    runtime_cycle_result: RuntimeCycleResult
    explanation_result: ExplanationResult
    llm_enabled: bool
    flow_health: FlowRealtimeBootstrapHealth
    technical_fetch_failures: tuple[TechnicalFetchFailure, ...]
    cycle_duration_seconds: float


__all__ = ["ProductionAdvisoryCycleOutcome", "ProductionAdvisoryCycleResult"]
