"""High-Impact Event Risk Gate output contracts (Corrective V1 Integration).

Narrow, production-layer facts only - never a duplicate of
``app.core.models.economic_event.EconomicEvent``: ``HighImpactEventRecord``
carries only the fields the gate's temporal/relevance logic actually reads
(see the approved design report, "Minimum event facts") - no actual/
forecast/previous/revision_number/revised_previous/impact direction, no
category taxonomy, no lifecycle status. This gate never constructs an
``EconomicEvent`` and never depends on ``app.macro``.

Layering mirrors every prior Stage 5-9 result model in this repository: one
record fact, one per-family verdict, one aggregate result - each embedding
its inputs unchanged, never copying a fact out in isolation.
"""

from __future__ import annotations

from typing import Self

from pydantic import Field, model_validator

from app.core.enums.high_impact_event import (
    HighImpactEventBlockReason,
    HighImpactEventDataQuality,
    HighImpactEventImportance,
    HighImpactEventVerdict,
)
from app.core.enums.strategy_router import StrategyFamily
from app.core.models.base import DomainModel, Symbol, Timestamp

_FAMILY_ORDER: tuple[StrategyFamily, ...] = tuple(StrategyFamily)


class HighImpactEventRecord(DomainModel):
    """One scheduled-event fact from the MQL5 calendar bridge, at the
    minimum fidelity the gate needs.

    ``scope`` is the bridge's own descriptive currency/instrument-class
    tag(s), carried for provenance/debugging only - the gate's own
    relevance decision never reads it. For currency-derivable event codes
    the gate uses its own fixed, hardcoded ``event_code`` -> currency-scope
    table; for event codes with no typed-context-derivable scope (e.g.
    ``EIA_CRUDE_INVENTORIES``) it uses the caller-supplied
    ``HighImpactEventSymbolScopeConfig`` instead (see
    ``app.decision.high_impact_event_gate``) - never this field, so a
    mis-tagged bridge ``scope`` value can never cause an incorrect gate
    verdict either way.
    """

    provider_event_id: str = Field(min_length=1)
    event_time: Timestamp
    importance: HighImpactEventImportance
    scope: tuple[str, ...] = ()
    event_code: str = Field(min_length=1)
    name: str = Field(min_length=1)


class HighImpactEventSymbolOverride(DomainModel):
    """One caller-supplied ``event_code -> explicit symbols`` relevance
    entry.

    Exists specifically for event classes whose relevance cannot be
    deterministically derived from any existing typed
    ``MarketEvaluationContext`` fact (see the approved corrective design
    report, "Discovered blocker" - currently only
    ``EIA_CRUDE_INVENTORIES`` in V1: no typed field anywhere identifies a
    WTI/Brent/energy instrument, and ``base_asset`` cannot be reused for it
    because that field's own validator requires a paired ``network``,
    meaningless for a commodity). The actual symbol values are never
    guessed by this repository - they must come from operator/runtime
    configuration.
    """

    event_code: str = Field(min_length=1)
    symbols: tuple[Symbol, ...] = Field(min_length=1)


class HighImpactEventSymbolScopeConfig(DomainModel):
    """Caller-supplied, explicit relevance policy for event codes with no
    typed-context-derivable scope - runtime relevance policy, never
    provider event data, so it is deliberately not a field on
    ``HighImpactEventRecord``. Never populated by the gate itself, never
    loaded from environment/files/network by the gate - a pure value
    object the composition layer constructs and passes in.

    Absent an entry for a given ``event_code`` (including when this whole
    config is omitted), that event code is never guessed as relevant to
    any symbol - it simply never matches, never blocking/warning anything,
    per the approved fail-open-on-the-unconfigured-side design.
    """

    overrides: tuple[HighImpactEventSymbolOverride, ...] = ()

    @model_validator(mode="after")
    def _validate_no_duplicate_event_codes(self) -> Self:
        codes = [override.event_code for override in self.overrides]
        if len(set(codes)) != len(codes):
            raise ValueError("overrides must not contain duplicate event_code entries")
        return self

    def symbols_for(self, event_code: str) -> tuple[Symbol, ...]:
        """Explicit symbol tuple configured for ``event_code``, or ``()``
        when none was supplied - never a guessed/derived value."""
        for override in self.overrides:
            if override.event_code == event_code:
                return override.symbols
        return ()


class HighImpactEventContext(DomainModel):
    """The one caller-supplied bundle the MQL5 bridge file-reader adapter
    produces and the runtime cycle threads, unchanged, into the Decision/
    Risk Pipeline - the necessary carrier for ``events``/``data_quality``/
    ``producer``/``generated_at`` together, mirroring how ``flow``/
    ``technical``/``external`` are each already one typed optional object
    per upstream contour rather than several loose parameters.

    ``events`` is empty whenever ``data_quality`` is not ``FRESH`` - a
    degraded bridge read never partially trusts whatever it could parse
    (see the approved design report, "Fail-open policy").
    """

    events: tuple[HighImpactEventRecord, ...] = ()
    data_quality: HighImpactEventDataQuality
    producer: str = Field(min_length=1)
    generated_at: Timestamp | None = None

    @model_validator(mode="after")
    def _validate_events_empty_unless_fresh(self) -> Self:
        if self.data_quality is not HighImpactEventDataQuality.FRESH and self.events:
            raise ValueError("events must be empty unless data_quality is FRESH")
        return self

    @model_validator(mode="after")
    def _validate_generated_at_presence(self) -> Self:
        if self.data_quality in (HighImpactEventDataQuality.UNAVAILABLE, HighImpactEventDataQuality.MALFORMED):
            if self.generated_at is not None:
                raise ValueError("generated_at must be None when data_quality is UNAVAILABLE or MALFORMED")
        return self


class HighImpactEventFamilyResult(DomainModel):
    """One Setup-``CONSTRUCTED`` family's Stage-adjacent temporal-safety
    verdict.

    Never produced for a family whose ``SetupConstructionResult.outcome``
    is not ``CONSTRUCTED`` - there is no ``signal_time``/``valid_until`` to
    evaluate an overlap against for such a family (see the approved design
    report, "Setup-blocked-family semantics"). Carries no direction,
    confidence, or probability field of any kind.
    """

    family: StrategyFamily
    verdict: HighImpactEventVerdict
    relevant_events: tuple[HighImpactEventRecord, ...] = ()
    reasons: tuple[HighImpactEventBlockReason, ...] = ()
    next_safe_time: Timestamp | None = None
    data_quality: HighImpactEventDataQuality

    @model_validator(mode="after")
    def _validate_reasons_match_verdict(self) -> Self:
        if self.verdict is HighImpactEventVerdict.BLOCKED:
            if self.reasons != (HighImpactEventBlockReason.EVENT_WINDOW_OVERLAP,):
                raise ValueError("BLOCKED requires exactly (EVENT_WINDOW_OVERLAP,)")
        elif self.reasons:
            raise ValueError("reasons must be empty unless verdict is BLOCKED")
        return self

    @model_validator(mode="after")
    def _validate_next_safe_time_matches_verdict(self) -> Self:
        if self.verdict is HighImpactEventVerdict.BLOCKED:
            if self.next_safe_time is None:
                raise ValueError("BLOCKED requires next_safe_time")
        elif self.next_safe_time is not None:
            raise ValueError("next_safe_time must be None unless verdict is BLOCKED")
        return self

    @model_validator(mode="after")
    def _validate_relevant_events_deterministic_order(self) -> Self:
        expected = tuple(sorted(self.relevant_events, key=lambda e: (e.event_time, e.provider_event_id)))
        if self.relevant_events != expected:
            raise ValueError("relevant_events must be ordered by (event_time, provider_event_id)")
        return self


class HighImpactEventRiskResult(DomainModel):
    """Deterministic High-Impact Event Risk Gate aggregation: one verdict
    per Setup-``CONSTRUCTED`` family, in canonical ``StrategyFamily`` order.

    The sole authoritative record of ``HighImpactEventBlockReason.
    EVENT_WINDOW_OVERLAP`` - never recoverable from ``RiskFamilyResult``/
    ``PortfolioFamilyResult``/``SessionFamilyResult``/
    ``FinalRecommendationFamilyResult`` after the fact, all of which only
    ever carry their own stage-local, opaque reason (see the approved
    design report, "Authoritative reason preservation").
    """

    as_of: Timestamp
    family_results: tuple[HighImpactEventFamilyResult, ...] = ()
    producer: str = Field(min_length=1)
    generated_at: Timestamp | None = None

    @model_validator(mode="after")
    def _validate_no_duplicate_families(self) -> Self:
        families = [result.family for result in self.family_results]
        if len(set(families)) != len(families):
            raise ValueError("family_results must not contain duplicate families")
        return self

    @model_validator(mode="after")
    def _validate_canonical_family_order(self) -> Self:
        indexes = [_FAMILY_ORDER.index(result.family) for result in self.family_results]
        if indexes != sorted(indexes):
            raise ValueError("family_results must be in canonical StrategyFamily order")
        return self


__all__ = [
    "HighImpactEventContext",
    "HighImpactEventFamilyResult",
    "HighImpactEventRecord",
    "HighImpactEventRiskResult",
    "HighImpactEventSymbolOverride",
    "HighImpactEventSymbolScopeConfig",
]
