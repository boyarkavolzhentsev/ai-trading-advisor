"""Deterministic High-Impact Event Risk Gate (Corrective V1 Integration).

Sits between Setup Construction and Risk: evaluates whether each Setup-
``CONSTRUCTED`` family's concrete ``CandidateTradeSetup.signal_time``/
``.valid_until`` window is safe to issue against a small, fixed V1
allowlist of scheduled high-impact macro events, then bridges the verdict
into the existing, unmodified ``RiskGate`` contract by composing (never
modifying or duplicating) ``app.decision.setup_construction.
to_candidate_risk_inputs``.

This gate does NOT decide direction. It never reads Judge's own
``direction``, never reads Flow/Technical/External Intelligence evidence,
never reads MT5, the filesystem, or the wall clock, and never constructs an
``EconomicEvent`` or depends on ``app.macro``/External Intelligence in any
way - a pure, synchronous, stateless function of its explicit inputs only.

Only families with ``SetupConstructionOutcome.CONSTRUCTED`` are evaluated -
a Setup-BLOCKED family has no ``signal_time``/``valid_until`` to check an
overlap against, so no ``HighImpactEventFamilyResult`` is ever produced for
one (see the approved design report, "Setup-blocked-family semantics").

Relevance scoping is fully explicit - no fuzzy/NLP matching, no
symbol-name heuristics (no ``contains``/``startswith`` of any kind), no
runtime symbol-classification inference. Two of the five V1 scope
categories (USD/EUR/GBP/JPY currency exposure, BTC/ETH asset identity) are
deterministically derivable from ``MarketEvaluationContext.
currency_exposures``/``.base_asset`` alone, and are resolved by this
gate's own fixed, hardcoded ``_EVENT_CODE_SCOPE`` table.

The fifth (WTI/Brent/energy-class, i.e. ``EIA_CRUDE_INVENTORIES``) has no
dedicated typed field anywhere in ``MarketEvaluationContext`` -
``base_asset`` cannot be reused for it because that field's own validator
requires a paired ``network``, which is semantically meaningless for a
commodity, and no oil/energy contour or symbol convention exists yet
anywhere in this repository (``app/markets/energies`` is an empty
placeholder). This gate makes NO assumption about what a live WTI/Brent
broker symbol looks like: relevance for ``_SYMBOL_OVERRIDE_EVENT_CODES``
(currently just ``EIA_CRUDE_INVENTORIES``) is resolved exclusively from the
caller-supplied ``HighImpactEventSymbolScopeConfig`` (see
``app.core.models.high_impact_event``) - an explicit, exact-match
``event_code -> symbols`` mapping the composition layer/operator supplies,
never loaded from environment/files/network by this gate, and never
guessed here. An event code in ``_SYMBOL_OVERRIDE_EVENT_CODES`` with no
matching config entry simply never matches any symbol - it is never
silently treated as globally relevant, and it is never inferred from the
symbol's own name.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from decimal import Decimal
from typing import Final

from app.core.enums.high_impact_event import (
    HighImpactEventBlockReason,
    HighImpactEventDataQuality,
    HighImpactEventImportance,
    HighImpactEventVerdict,
)
from app.core.enums.setup_construction import SetupConstructionOutcome
from app.core.enums.strategy_router import StrategyFamily
from app.core.models.base import Timestamp
from app.core.models.high_impact_event import (
    HighImpactEventContext,
    HighImpactEventFamilyResult,
    HighImpactEventRecord,
    HighImpactEventRiskResult,
    HighImpactEventSymbolScopeConfig,
)
from app.core.models.market_evaluation_context import MarketEvaluationContext
from app.core.models.risk_gate_result import CandidateRiskInput
from app.core.models.setup_construction import StrategySetupResult
from app.decision.setup_construction import to_candidate_risk_inputs

BLOCK_PRE_WINDOW: Final[timedelta] = timedelta(minutes=5)
BLOCK_POST_WINDOW: Final[timedelta] = timedelta(minutes=5)
WARN_PRE_WINDOW: Final[timedelta] = timedelta(minutes=15)
WARN_POST_WINDOW: Final[timedelta] = timedelta(minutes=10)
"""Approved V1 fixed policy constants - BLOCK: T-5m..T+5m; WARN: T-15m..T-5m
and T+5m..T+10m; ALLOW otherwise. Deterministic policy config, never
market-derived."""

HARD_BLOCK_EVENT_CODES: Final[frozenset[str]] = frozenset(
    {
        "FOMC",
        "US_CPI",
        "US_CORE_CPI",
        "US_PCE",
        "US_CORE_PCE",
        "US_NFP",
        "US_UNEMPLOYMENT",
        "ECB_RATE_DECISION",
        "EUROZONE_CPI",
        "BOE_RATE_DECISION",
        "UK_CPI",
        "BOJ_RATE_DECISION",
        "EIA_CRUDE_INVENTORIES",
    }
)
"""Approved V1 HIGH-importance hard-block allowlist, by canonical event
code. The bridge normalizes provider event names/codes into these codes
upstream - this gate never does fuzzy/text matching of its own."""

WARN_ONLY_EVENT_CODES: Final[frozenset[str]] = frozenset({"US_GDP", "US_ISM", "US_MAJOR_PMI"})
"""Approved V1 WARN-only allowlist - these can never independently
hard-block issuance, regardless of reported importance."""

_ALLOWLISTED_EVENT_CODES: Final[frozenset[str]] = HARD_BLOCK_EVENT_CODES | WARN_ONLY_EVENT_CODES

_EVENT_CODE_SCOPE: Final[Mapping[str, str]] = {
    "FOMC": "USD",
    "US_CPI": "USD",
    "US_CORE_CPI": "USD",
    "US_PCE": "USD",
    "US_CORE_PCE": "USD",
    "US_NFP": "USD",
    "US_UNEMPLOYMENT": "USD",
    "US_GDP": "USD",
    "US_ISM": "USD",
    "US_MAJOR_PMI": "USD",
    "ECB_RATE_DECISION": "EUR",
    "EUROZONE_CPI": "EUR",
    "BOE_RATE_DECISION": "GBP",
    "UK_CPI": "GBP",
    "BOJ_RATE_DECISION": "JPY",
}
"""Gate-owned, authoritative event_code -> currency-scope tag table, for
event codes whose relevance IS deterministically derivable from
``MarketEvaluationContext``. Never sourced from ``HighImpactEventRecord.
scope`` (the bridge's own, unverified, descriptive field). Deliberately
excludes ``_SYMBOL_OVERRIDE_EVENT_CODES`` - those are resolved via
caller-supplied config instead, never via this table."""

_SYMBOL_OVERRIDE_EVENT_CODES: Final[frozenset[str]] = frozenset({"EIA_CRUDE_INVENTORIES"})
"""Canonical event codes with no typed-context-derivable scope - relevance
for these is resolved exclusively via the caller-supplied
``HighImpactEventSymbolScopeConfig``, never via ``_EVENT_CODE_SCOPE`` and
never via any symbol-name heuristic. This set only names WHICH event codes
require caller configuration - it makes no claim about which symbols they
apply to."""

_CURRENCY_SCOPES: Final[frozenset[str]] = frozenset({"USD", "EUR", "GBP", "JPY"})

_CRYPTO_USD_SENSITIVE_ASSETS: Final[frozenset[str]] = frozenset({"BTC", "ETH"})
"""Per the approved design report's Section 7: BTC/ETH are USD-macro-scope
only in V1 - no JPY/other-currency spillover is implemented."""

_IGNORED_IMPORTANCE: Final[frozenset[HighImpactEventImportance]] = frozenset(
    {HighImpactEventImportance.NONE, HighImpactEventImportance.LOW}
)


def _instrument_scope_tags(context: MarketEvaluationContext) -> frozenset[str]:
    """Deterministic, hardcoded resolution of which currency/asset-derived
    V1 scope tags this evaluation's instrument belongs to - no runtime
    inference of any kind. Covers only the typed-context-derivable
    categories; ``_SYMBOL_OVERRIDE_EVENT_CODES`` are resolved separately,
    via caller config, never via this function."""
    tags: set[str] = {currency for currency in context.currency_exposures if currency in _CURRENCY_SCOPES}
    if context.base_asset in _CRYPTO_USD_SENSITIVE_ASSETS:
        tags.add("USD")
    return frozenset(tags)


def _is_relevant(
    event: HighImpactEventRecord,
    *,
    symbol: str,
    scope_tags: frozenset[str],
    symbol_scope_config: HighImpactEventSymbolScopeConfig | None,
) -> bool:
    """Whether ``event`` is relevant to this evaluation's instrument.

    Exact-match only, on two entirely separate deterministic paths - no
    symbol-name heuristic of any kind is used on either path:

    - currency-derivable event codes: ``event.event_code``'s fixed scope
      tag (``_EVENT_CODE_SCOPE``) must be one of ``scope_tags`` (derived
      from typed ``MarketEvaluationContext`` facts).
    - ``_SYMBOL_OVERRIDE_EVENT_CODES``: ``symbol`` must appear, verbatim,
      in the caller-supplied ``symbol_scope_config``'s explicit entry for
      this ``event_code`` - absent config or absent entry means no match,
      never a fallback guess.
    """
    if event.importance in _IGNORED_IMPORTANCE:
        return False
    if event.event_code not in _ALLOWLISTED_EVENT_CODES:
        return False
    if event.event_code in _SYMBOL_OVERRIDE_EVENT_CODES:
        configured_symbols = symbol_scope_config.symbols_for(event.event_code) if symbol_scope_config is not None else ()
        return symbol in configured_symbols
    return _EVENT_CODE_SCOPE.get(event.event_code) in scope_tags


_IMPORTANCE_RANK: Final[Mapping[HighImpactEventImportance, int]] = {
    HighImpactEventImportance.NONE: 0,
    HighImpactEventImportance.LOW: 1,
    HighImpactEventImportance.MODERATE: 2,
    HighImpactEventImportance.HIGH: 3,
}

_HARD_BLOCK_MIN_IMPORTANCE_OVERRIDE: Final[Mapping[str, HighImpactEventImportance]] = {
    "FOMC": HighImpactEventImportance.MODERATE,
}
"""Narrowest exception to the HIGH-only hard-block eligibility rule below -
MetaQuotes reports ``fomc-meeting-statement`` as MODERATE (never rewritten;
see ``HighImpactEventRecord.importance``'s own docstring), yet it must still
be BLOCK-eligible under the approved FOMC policy. ``fomc-press-conference``
is HIGH and remains BLOCK-eligible through the unchanged default path. No
other hard-block canonical code appears here - every other code keeps the
implicit HIGH-only minimum."""


def _is_hard_block_eligible(event: HighImpactEventRecord) -> bool:
    if event.event_code not in HARD_BLOCK_EVENT_CODES:
        return False
    minimum_importance = _HARD_BLOCK_MIN_IMPORTANCE_OVERRIDE.get(event.event_code, HighImpactEventImportance.HIGH)
    return _IMPORTANCE_RANK[event.importance] >= _IMPORTANCE_RANK[minimum_importance]


def _overlaps(signal_time: Timestamp, valid_until: Timestamp, window_start: Timestamp, window_end: Timestamp) -> bool:
    """Positive-duration interval overlap - strict on both sides.

    A ``[signal_time, valid_until]`` interval that only *touches* a window
    boundary at a single instant (e.g. ``valid_until == window_start``) has
    a zero-duration, measure-zero intersection - not a genuine overlap of
    the recommendation's validity period with the window. Using strict
    inequalities here (rather than ``<=``/``>=``) is what makes a setup
    signaled well clear of a window (e.g. 20 minutes before an event, with
    a 5-minute validity window ending exactly 15 minutes before it) resolve
    to ``ALLOWED`` rather than landing exactly on the WARN boundary."""
    return signal_time < window_end and valid_until > window_start


def _event_verdict(
    event: HighImpactEventRecord, *, signal_time: Timestamp, valid_until: Timestamp
) -> tuple[HighImpactEventVerdict, Timestamp | None]:
    block_start = event.event_time - BLOCK_PRE_WINDOW
    block_end = event.event_time + BLOCK_POST_WINDOW
    if _is_hard_block_eligible(event) and _overlaps(signal_time, valid_until, block_start, block_end):
        return HighImpactEventVerdict.BLOCKED, block_end

    warn_start = event.event_time - WARN_PRE_WINDOW
    warn_end = event.event_time + WARN_POST_WINDOW
    if _overlaps(signal_time, valid_until, warn_start, warn_end):
        return HighImpactEventVerdict.WARNED, None

    return HighImpactEventVerdict.ALLOWED, None


_VERDICT_SEVERITY: Final[Mapping[HighImpactEventVerdict, int]] = {
    HighImpactEventVerdict.ALLOWED: 0,
    HighImpactEventVerdict.WARNED: 1,
    HighImpactEventVerdict.BLOCKED: 2,
}


def _evaluate_family(
    *,
    family: StrategyFamily,
    signal_time: Timestamp,
    valid_until: Timestamp,
    symbol: str,
    scope_tags: frozenset[str],
    symbol_scope_config: HighImpactEventSymbolScopeConfig | None,
    events: tuple[HighImpactEventRecord, ...],
    data_quality: HighImpactEventDataQuality,
) -> HighImpactEventFamilyResult:
    relevant = tuple(
        sorted(
            (
                event
                for event in events
                if _is_relevant(event, symbol=symbol, scope_tags=scope_tags, symbol_scope_config=symbol_scope_config)
            ),
            key=lambda e: (e.event_time, e.provider_event_id),
        )
    )

    worst_verdict = HighImpactEventVerdict.ALLOWED
    block_end_times: list[Timestamp] = []
    for event in relevant:
        verdict, block_end = _event_verdict(event, signal_time=signal_time, valid_until=valid_until)
        if _VERDICT_SEVERITY[verdict] > _VERDICT_SEVERITY[worst_verdict]:
            worst_verdict = verdict
        if verdict is HighImpactEventVerdict.BLOCKED:
            assert block_end is not None
            block_end_times.append(block_end)

    if worst_verdict is HighImpactEventVerdict.BLOCKED:
        return HighImpactEventFamilyResult(
            family=family,
            verdict=HighImpactEventVerdict.BLOCKED,
            relevant_events=relevant,
            reasons=(HighImpactEventBlockReason.EVENT_WINDOW_OVERLAP,),
            next_safe_time=max(block_end_times),
            data_quality=data_quality,
        )
    return HighImpactEventFamilyResult(
        family=family,
        verdict=worst_verdict,
        relevant_events=relevant,
        data_quality=data_quality,
    )


class HighImpactEventGate:
    """Deterministic V1 High-Impact Event Risk Gate."""

    def evaluate(
        self,
        *,
        strategy_setup_result: StrategySetupResult,
        context: HighImpactEventContext | None,
        as_of: Timestamp,
        symbol_scope_config: HighImpactEventSymbolScopeConfig | None = None,
    ) -> HighImpactEventRiskResult:
        """Evaluate every Setup-``CONSTRUCTED`` family in
        ``strategy_setup_result`` against ``context``'s tracked events.

        ``context is None`` (bridge never supplied) is treated identically
        to an ``UNAVAILABLE``-quality context: fail-open, every evaluated
        family ``ALLOWED``, no fabricated event. ``symbol_scope_config``
        defaults to ``None`` (no override entries) - a caller-supplied,
        static value object only; never read from the filesystem/network
        by this gate (see this module's own docstring).
        """
        market_evaluation = strategy_setup_result.strategy_policy_result.strategy_judge_result.strategy_router_result.market_evaluation
        eval_context = market_evaluation.context

        events = context.events if context is not None else ()
        data_quality = context.data_quality if context is not None else HighImpactEventDataQuality.UNAVAILABLE
        producer = context.producer if context is not None else "unavailable"
        generated_at = context.generated_at if context is not None else None

        scope_tags = _instrument_scope_tags(eval_context)

        family_results = tuple(
            _evaluate_family(
                family=setup_result.family,
                signal_time=setup_result.setup.signal_time,
                valid_until=setup_result.setup.valid_until,
                symbol=eval_context.symbol,
                scope_tags=scope_tags,
                symbol_scope_config=symbol_scope_config,
                events=events,
                data_quality=data_quality,
            )
            for setup_result in strategy_setup_result.family_results
            if setup_result.outcome is SetupConstructionOutcome.CONSTRUCTED
        )

        return HighImpactEventRiskResult(
            as_of=as_of,
            family_results=family_results,
            producer=producer,
            generated_at=generated_at,
        )


def to_event_adjusted_candidate_risk_inputs(
    strategy_setup_result: StrategySetupResult,
    high_impact_event_risk_result: HighImpactEventRiskResult | None,
) -> tuple[CandidateRiskInput, ...]:
    """Compose (never modify or duplicate) the existing, unmodified
    ``app.decision.setup_construction.to_candidate_risk_inputs``: start from
    its exact output, then override ``risk_per_unit`` to ``Decimal("0")``
    for exactly the families this gate found ``BLOCKED``.

    Family count, family set, and family order are always inherited
    unchanged from the base bridge output - this function never omits a
    family, satisfying ``RiskGate``'s exact-coverage contract (see the
    approved design report, "RiskGate coverage requirement"). A
    Setup-BLOCKED family's existing zero-sentinel entry is always left
    untouched, since this gate never produces a ``HighImpactEventFamilyResult``
    for one in the first place.
    """
    base = to_candidate_risk_inputs(strategy_setup_result)
    if high_impact_event_risk_result is None:
        return base

    blocked_families = {
        result.family for result in high_impact_event_risk_result.family_results if result.verdict is HighImpactEventVerdict.BLOCKED
    }
    if not blocked_families:
        return base

    return tuple(
        candidate if candidate.family not in blocked_families else CandidateRiskInput(family=candidate.family, risk_per_unit=Decimal("0"))
        for candidate in base
    )


__all__ = [
    "BLOCK_POST_WINDOW",
    "BLOCK_PRE_WINDOW",
    "HARD_BLOCK_EVENT_CODES",
    "WARN_ONLY_EVENT_CODES",
    "WARN_POST_WINDOW",
    "WARN_PRE_WINDOW",
    "HighImpactEventGate",
    "to_event_adjusted_candidate_risk_inputs",
]
