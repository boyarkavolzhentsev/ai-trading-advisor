"""Application-layer transport-neutral DTOs.

Everything here is a stable, operator-facing contract sitting directly above
``ProductionAdvisoryCycleResult`` (Stage 0D) - never the internal object
graph itself. No FastAPI import, no HTTP dependency of any kind: these
models are plain, frozen ``DomainModel`` (pydantic) values, JSON-friendly
later but not coupled to any particular transport today.

Two disjoint kinds of field live here, never mixed on one class, mirroring
``app.core.models.explanation``'s own authoritative/narrative split one layer
up:

AUTHORITATIVE (``RecommendationDTO``) - sourced only from
``FinalRecommendation`` (via ``FinalRecommendationFamilyResult.recommendation``
on an ``ACTIONABLE`` verdict). Every numeric/enum trading fact is copied
unchanged - ``Decimal``/``Timestamp`` are never converted to ``float``/naive
``datetime`` for transport convenience, and ``account_currency`` is never
hardcoded.

NARRATIVE (``ExplanationDTO``, ``RecommendationNarrativeDTO``) - presentation
content only, sourced from ``ExplanationResult``. No field here can ever
influence, override, or be consulted to derive any ``RecommendationDTO``
field, any ``NoTradeReasonDTO``, or ``ApplicationAdvisoryStatus``.

``NoTradeReasonDTO`` reuses each pipeline stage's own authoritative source
enum verbatim (never re-stringified, never invented) - see
``app.application.advisory_service._derive_no_trade_reason`` for the
precedence walk that produces these.
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field

from app.core.enums.explanation import ExplanationProviderStatus
from app.core.enums.final_recommendation import FinalRecommendationBlockReason
from app.core.enums.high_impact_event import HighImpactEventBlockReason, HighImpactEventDataQuality
from app.core.enums.market import Timeframe
from app.core.enums.mt5_matching import MT5TrackedRecommendationCreationOutcome
from app.core.enums.mt5_runtime import MT5ConnectivityState
from app.core.enums.policy_gate import PolicyBlockReason
from app.core.enums.portfolio import PortfolioBlockReason
from app.core.enums.risk_gate import RiskBlockReason
from app.core.enums.runtime_cycle import NettingIssuanceOutcome, RuntimeCycleOutcome
from app.core.enums.runtime_fact_assembly import RuntimeFactAssemblyBlockReason
from app.core.enums.session_gate import SessionBlockReason
from app.core.enums.setup_construction import SetupBlockReason
from app.core.enums.strategy_router import StrategyFamily, StrategyIneligibilityReason
from app.core.enums.stream import StreamStatus
from app.core.enums.trade import TradeDirection
from app.core.models.base import DomainModel, Price, Symbol, Timestamp


class ApplicationAdvisoryStatus(StrEnum):
    """Coarse, Application-level classification of one advisory response.

    Derived purely mechanically from already-existing Stage0D/runtime facts
    (see ``app.application.advisory_service._derive_status``) - never from
    narrative text, never a new business judgment. ``SERVICE_UNAVAILABLE``
    and ``DEGRADED`` describe cycle *quality*; ``READY``/``NO_TRADE``
    describe whether a genuinely issuable recommendation exists. A
    ``DEGRADED`` cycle may still carry one or more ``recommendations`` - the
    two concepts are independent, never collapsed into each other.
    """

    READY = "READY"
    NO_TRADE = "NO_TRADE"
    DEGRADED = "DEGRADED"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"


class NoTradeStage(StrEnum):
    """Presentation-level pipeline stage a no-trade reason terminated at -
    never a free-text label. Exactly one of ten fixed pipeline stages, in
    their own deterministic run order."""

    EVALUATION = "EVALUATION"
    JUDGE = "JUDGE"
    POLICY = "POLICY"
    SETUP = "SETUP"
    EVENT = "EVENT"
    RISK = "RISK"
    PORTFOLIO = "PORTFOLIO"
    SESSION = "SESSION"
    FINAL = "FINAL"
    ISSUANCE = "ISSUANCE"


class IssuanceFailureReason(StrEnum):
    """Application-owned issuance-stage failure classification - the one
    typed fact no existing Stage 10E/Part F domain enum represents: a
    genuinely ``CREATED`` ``MT5TrackedRecommendationCreationOutcome`` whose
    own ``tracking_persisted`` write nonetheless failed
    (``TrackingIssuancePersistenceOutcome`` - see
    ``app.core.models.runtime_cycle`` - documents all four
    ``tracking_persisted``/``provenance_persisted`` combinations as
    representable after ``CREATED``).

    Never used in place of ``MT5TrackedRecommendationCreationOutcome.CREATED``
    itself as a no-trade "reason": ``CREATED`` means creation succeeded, so
    reporting it verbatim as a block cause would be self-contradictory. This
    member exists solely so ``NoTradeReasonDTO.codes`` never has to misuse
    ``CREATED`` (a success fact) or ``SNAPSHOT_UNAVAILABLE`` (a distinct,
    unrelated failure fact) to describe this one gap. The three underlying
    source facts (``tracking_creation_outcome``/``tracking_persisted``/
    ``provenance_persisted``) remain fully visible, verbatim, via
    ``OperationalDiagnosticsDTO.issuance_persistence`` for the same
    ``trade_id`` - this enum never replaces them, only labels the
    Application-level consequence of their combination.
    """

    TRACKING_PERSISTENCE_FAILED = "TRACKING_PERSISTENCE_FAILED"


NoTradeCode = (
    StrategyIneligibilityReason
    | PolicyBlockReason
    | SetupBlockReason
    | HighImpactEventBlockReason
    | RiskBlockReason
    | PortfolioBlockReason
    | SessionBlockReason
    | FinalRecommendationBlockReason
    | NettingIssuanceOutcome
    | MT5TrackedRecommendationCreationOutcome
    | IssuanceFailureReason
)
"""Every authoritative source enum a no-trade reason may ever carry - never
an invented string, with the sole narrow exception of
``IssuanceFailureReason`` (see its own docstring for why no existing domain
enum can represent "created but not persisted"). Exactly one union member
type is populated per ``NoTradeReasonDTO`` instance (all ``codes`` entries
share the same source enum), matching ``stage``."""


class NoTradeReasonDTO(DomainModel):
    """One family's terminal no-trade cause, at the first pipeline stage a
    genuine (non-mirrored) block was found - see
    ``app.application.advisory_service._derive_no_trade_reason`` for the
    exact precedence walk and why upstream-mirrored reasons
    (``PolicyBlockReason.JUDGE_OUTCOME_*`` aside, which are reclassified to
    ``NoTradeStage.JUDGE`` rather than treated as mirrors) never leak through
    as if they were newly-discovered at a later stage.

    ``codes`` carries more than one entry only for ``NoTradeStage.EVALUATION``
    (the sole stage whose own source model permits multiple simultaneous
    reasons) - every other stage's source model enforces at most one reason,
    so ``codes`` is a single-element tuple there.
    """

    strategy_family: StrategyFamily
    stage: NoTradeStage
    codes: Annotated[tuple[NoTradeCode, ...], Field(min_length=1)]


class RecommendationDTO(DomainModel):
    """One genuinely issuable recommendation's authoritative facts - sourced
    exclusively from ``FinalRecommendation`` (never from
    ``RecommendationExplanation``/``headline``/``cycle_summary``/any LLM
    output/``no_trade_explanation``/``warnings``). ``Decimal``/``Timestamp``
    values are preserved unchanged; ``account_currency`` is copied verbatim,
    never hardcoded, never converted.

    ``symbol`` (corrective design closure, "PROVIDER SYMBOL SPLIT + PRICE-
    BASIS RECONCILIATION") is the MT5 broker-facing symbol (``SymbolMapping.
    mt5_symbol``, e.g. ``"BTCUSDt"``) - what the operator actually types into
    their broker for manual execution. Never the Binance/logical spelling -
    see ``AdvisoryResponse.symbol``/``.market_data_symbol`` for those.
    """

    trade_id: Annotated[str, Field(min_length=1)]
    strategy_family: StrategyFamily
    symbol: Symbol
    direction: TradeDirection
    entry_price: Price
    stop_loss: Price
    take_profit_levels: tuple[Price, ...] = ()
    approved_volume: Annotated[Decimal, Field(gt=0)]
    approved_risk_amount: Annotated[Decimal, Field(gt=0)]
    account_currency: Annotated[str, Field(min_length=1)]
    signal_time: Timestamp
    valid_until: Timestamp


class TradingDataQualityDTO(DomainModel):
    """Small, honest trading-evidence-quality summary - deliberately NOT
    including Flow/Technical evidence quality (``MarketEvaluationResult``'s
    own quality fields were not audited before this DTO was designed; see the
    approved corrective design closure) and deliberately NOT including
    ``FlowRealtimeBootstrapHealth`` (operational health only - see
    ``OperationalDiagnosticsDTO``, and ``FlowRealtimeBootstrapHealth``'s own
    docstring: "never a trading-readiness signal").

    ``calendar_data_quality`` is ``None`` precisely when the High-Impact
    Event Risk Gate never ran this cycle (``strategy_setup_result`` contained
    zero ``CONSTRUCTED`` families) - never fabricated.

    ``account_risk_snapshot_ready``/``account_risk_snapshot_block_reasons``
    exist so a whole-cycle "Risk onward never ran" fact
    (``DecisionRiskPipelineOutcome.BLOCKED_BEFORE_RISK``, or
    ``RuntimeCycleResult.decision_risk_pipeline_result`` being ``None``
    entirely because Runtime Fact Assembly was never even attempted) is never
    left unexplained behind a bare ``runtime_outcome == PARTIAL_DEGRADED`` -
    and never fabricated as a per-family ``NoTradeReasonDTO`` when the cause
    is genuinely cycle-level, not family-level.
    ``account_risk_snapshot_block_reasons`` is empty both when the assembly
    is ``READY`` and when it was never attempted at all (``account_risk_
    snapshot_assembly is None`` - distinguishable from a genuine block via
    ``account_risk_snapshot_ready``/``positions_read_status``/
    ``history_read_status`` together) - populated only when the assembly was
    actually attempted and came back ``BLOCKED``.
    """

    runtime_outcome: RuntimeCycleOutcome
    mt5_connectivity_state: MT5ConnectivityState
    positions_read_status: Literal["OK", "UNAVAILABLE", "UNMAPPABLE_POSITION_SIDE"] | None
    history_read_status: Literal["OK", "UNAVAILABLE", "MALFORMED_TIMESTAMP"] | None
    technical_fetch_failed_timeframes: tuple[Timeframe, ...]
    calendar_data_quality: HighImpactEventDataQuality | None
    account_risk_snapshot_ready: bool
    account_risk_snapshot_block_reasons: tuple[RuntimeFactAssemblyBlockReason, ...]


class IssuancePersistenceDTO(DomainModel):
    """One newly-issued recommendation's persistence audit trail this cycle -
    operational/audit state only, never authoritative trade geometry (that
    remains ``RecommendationDTO``'s exclusive concern). Verbatim copy of
    ``TrackingIssuancePersistenceOutcome`` - no field is re-derived or
    reinterpreted. Present for every ``ACTIONABLE`` family whose issuance was
    attempted this cycle, regardless of whether it ended up exposed as a
    ``RecommendationDTO`` or as an ``ISSUANCE``-stage ``NoTradeReasonDTO``."""

    trade_id: Annotated[str, Field(min_length=1)]
    tracking_creation_outcome: MT5TrackedRecommendationCreationOutcome
    tracking_persisted: bool
    provenance_persisted: bool


class OperationalDiagnosticsDTO(DomainModel):
    """Operational health only - never labeled or consulted as trading
    readiness. Sourced from ``FlowRealtimeBootstrapHealth``/
    ``ProductionAdvisoryCycleResult``'s own ``llm_enabled``/
    ``cycle_duration_seconds`` fields, never from ``RuntimeCycleResult``'s
    domain outcome.

    ``issuance_persistence`` makes a provenance-write failure
    (``tracking_persisted=True``/``provenance_persisted=False``) visible even
    when the recommendation itself remains exposed (see
    ``app.application.advisory_service.is_issuable``'s own docstring) - the
    fact must never be silently hidden merely because the recommendation
    still appears in ``AdvisoryResponse.recommendations``.
    """

    flow_market_stream_status: StreamStatus
    flow_order_book_stream_status: StreamStatus
    flow_open_interest_last_success_at: Timestamp | None
    llm_enabled: bool
    llm_provider_status: ExplanationProviderStatus
    cycle_duration_seconds: float
    issuance_persistence: tuple[IssuancePersistenceDTO, ...]


class RecommendationNarrativeDTO(DomainModel):
    """LLM-generated (or deterministic-fallback) narrative for one
    recommendation - presentation only. Carries no numeric/enum trading
    field: it can never shadow, replace, or disagree with the accompanying
    ``RecommendationDTO``."""

    trade_id: Annotated[str, Field(min_length=1)]
    strategy_family: StrategyFamily
    narrative: Annotated[str, Field(min_length=1)]
    cited_fact_ids: tuple[str, ...] = ()


class ExplanationDTO(DomainModel):
    """Presentation-only content - never a source of authoritative trading
    facts. ``deterministic_fallback_used`` is a pure derived fact
    (``provider_status is not ExplanationProviderStatus.LLM_SUCCESS``), never
    a second independently-reported signal. No raw prompt, provider payload,
    or API key is ever reachable through this model.
    """

    headline: Annotated[str, Field(min_length=1)]
    cycle_summary: Annotated[str, Field(min_length=1)]
    no_trade_explanation: str | None
    warnings: tuple[str, ...]
    data_quality_notes: tuple[str, ...]
    risk_notes: tuple[str, ...]
    provider_status: ExplanationProviderStatus
    llm_enabled: bool
    deterministic_fallback_used: bool
    recommendation_narratives: tuple[RecommendationNarrativeDTO, ...] = ()


class AdvisoryResponse(DomainModel):
    """The one stable, transport-neutral application DTO
    ``ApplicationAdvisoryService.create_advisory`` returns.

    ``symbol`` (corrective design closure, "PROVIDER SYMBOL SPLIT + PRICE-
    BASIS RECONCILIATION") is the operator-facing logical instrument
    identifier (``SymbolMapping.logical_symbol``, e.g. ``"BTC"``) - fed to no
    provider, never the Binance or MT5 native spelling. ``market_data_symbol``
    is the Binance symbol (``SymbolMapping.binance_symbol``, e.g.
    ``"BTCUSDT"``) the analytical evidence actually came from - present even
    when ``recommendations`` is empty. The MT5 broker-facing symbol (e.g.
    ``"BTCUSDt"``) is never duplicated here: it lives on each
    ``RecommendationDTO.symbol`` instead, since a cycle may legitimately
    carry zero recommendations. There is no caller-supplied symbol parameter
    anywhere in this package. ``recommendations`` and ``no_trade_reasons``
    are independent facts from ``status`` (see ``ApplicationAdvisoryStatus``'s
    own docstring): a ``DEGRADED`` response may still carry one or more
    ``recommendations``.
    """

    logical_cycle_id: str
    as_of: Timestamp
    symbol: Symbol
    market_data_symbol: Symbol
    status: ApplicationAdvisoryStatus
    recommendations: tuple[RecommendationDTO, ...]
    no_trade_reasons: tuple[NoTradeReasonDTO, ...]
    data_quality: TradingDataQualityDTO
    diagnostics: OperationalDiagnosticsDTO
    explanation: ExplanationDTO


__all__ = [
    "AdvisoryResponse",
    "ApplicationAdvisoryStatus",
    "ExplanationDTO",
    "IssuanceFailureReason",
    "IssuancePersistenceDTO",
    "NoTradeCode",
    "NoTradeReasonDTO",
    "NoTradeStage",
    "OperationalDiagnosticsDTO",
    "RecommendationDTO",
    "RecommendationNarrativeDTO",
    "TradingDataQualityDTO",
]
