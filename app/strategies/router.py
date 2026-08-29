"""Deterministic Strategy Router (Stage 6A).

Aggregates one already-produced ``MarketEvaluationResult`` into a per-
``StrategyFamily`` structural eligibility verdict: whether each family has
enough structurally-present, non-``UNAVAILABLE`` evidence for Stage 6B Judge
to be allowed to interpret it. Never invokes Judge, never touches a Flow/
Technical/External Intelligence analyst or supervisor package, never
performs I/O - a pure, synchronous, stateless function of its input (see
``app.strategies.protocols.StrategyRouterProtocol``).

Reads only contour participation/quality and external scope alignment -
never a Flow/Technical/External Intelligence analyst observation's
dimension or value. Whether a technical/flow/external contour actually
shows a trend, a breakout, a reversion, or an event is Stage 6B Judge's
question, never this router's: eligibility here means only "Judge may
inspect this family", never "this family is currently favorable".

``TREND_FOLLOWING`` and ``MEAN_REVERSION`` intentionally share the exact
same structural rule in V1 - see
``app.core.enums.strategy_router.StrategyFamily``.

A contour is usable for a family iff BOTH its status is in
``_USABLE_CONTOUR_STATUSES`` and its quality is in ``_USABLE_QUALITIES`` -
both sets are explicit and independently checked, never derived as
"quality != UNAVAILABLE", so a future ``FeatureQuality``/
``MarketEvaluationContourStatus`` member cannot silently fall on the wrong
side of either rule.
"""

from __future__ import annotations

from app.core.enums.market_evaluation import ExternalAlignmentStatus, MarketEvaluationContourStatus
from app.core.enums.quality import FeatureQuality
from app.core.enums.strategy_router import StrategyFamily, StrategyIneligibilityReason, StrategyRouterOutcome
from app.core.models.market_evaluation_result import MarketEvaluationResult
from app.core.models.strategy_router_result import StrategyEligibilityEntry, StrategyRouterResult

_USABLE_CONTOUR_STATUSES: frozenset[MarketEvaluationContourStatus] = frozenset(
    {MarketEvaluationContourStatus.ANALYZED, MarketEvaluationContourStatus.PARTIAL}
)
_USABLE_QUALITIES: frozenset[FeatureQuality] = frozenset(
    {FeatureQuality.VALID, FeatureQuality.PARTIAL, FeatureQuality.STALE}
)

_REQUIRED_CONTOURS: dict[StrategyFamily, tuple[str, ...]] = {
    StrategyFamily.TREND_FOLLOWING: ("technical",),
    StrategyFamily.MEAN_REVERSION: ("technical",),
    StrategyFamily.BREAKOUT: ("technical", "flow"),
    StrategyFamily.EVENT_DRIVEN: ("external",),
}

_REQUIRES_EXTERNAL_ALIGNMENT: frozenset[StrategyFamily] = frozenset({StrategyFamily.EVENT_DRIVEN})


def _contour_status_and_quality(
    market_evaluation: MarketEvaluationResult, contour: str
) -> tuple[MarketEvaluationContourStatus, FeatureQuality | None]:
    if contour == "technical":
        return market_evaluation.technical_status, market_evaluation.technical_quality
    if contour == "flow":
        return market_evaluation.flow_status, market_evaluation.flow_quality
    if contour == "external":
        return market_evaluation.external_status, market_evaluation.external_quality
    raise AssertionError(f"unknown contour {contour!r}")


def _contour_reasons(
    status: MarketEvaluationContourStatus, quality: FeatureQuality | None
) -> tuple[StrategyIneligibilityReason, ...]:
    reasons: list[StrategyIneligibilityReason] = []
    if status not in _USABLE_CONTOUR_STATUSES:
        if status is MarketEvaluationContourStatus.MISSING:
            reasons.append(StrategyIneligibilityReason.CONTOUR_MISSING)
        else:
            reasons.append(StrategyIneligibilityReason.CONTOUR_INSUFFICIENT_EVIDENCE)
    if quality is not None and quality not in _USABLE_QUALITIES:
        reasons.append(StrategyIneligibilityReason.QUALITY_UNAVAILABLE)
    return tuple(reasons)


def _external_alignment_reason(market_evaluation: MarketEvaluationResult) -> StrategyIneligibilityReason | None:
    """``EXTERNAL_SCOPE_NOT_ALIGNED`` is evaluated only when an external
    contour is structurally present: when ``external_status`` is
    ``MISSING``, ``CONTOUR_MISSING`` is already the precise reason - adding
    this reason too would carry no independent information, since there is
    no external scope available to align in the first place."""
    if market_evaluation.external_status is MarketEvaluationContourStatus.MISSING:
        return None
    if market_evaluation.external_alignment_status is not ExternalAlignmentStatus.MATCHED:
        return StrategyIneligibilityReason.EXTERNAL_SCOPE_NOT_ALIGNED
    return None


def _evaluate_family(market_evaluation: MarketEvaluationResult, family: StrategyFamily) -> StrategyEligibilityEntry:
    reason_set: set[StrategyIneligibilityReason] = set()

    for contour in _REQUIRED_CONTOURS[family]:
        status, quality = _contour_status_and_quality(market_evaluation, contour)
        reason_set.update(_contour_reasons(status, quality))

    if family in _REQUIRES_EXTERNAL_ALIGNMENT:
        alignment_reason = _external_alignment_reason(market_evaluation)
        if alignment_reason is not None:
            reason_set.add(alignment_reason)

    reasons = tuple(reason for reason in StrategyIneligibilityReason if reason in reason_set)
    return StrategyEligibilityEntry(family=family, eligible=not reasons, ineligibility_reasons=reasons)


class StrategyRouter:
    """Deterministic Stage 6A aggregator over one ``MarketEvaluationResult``."""

    def route(self, *, market_evaluation: MarketEvaluationResult) -> StrategyRouterResult:
        eligibility = tuple(_evaluate_family(market_evaluation, family) for family in StrategyFamily)
        eligible_families = tuple(entry.family for entry in eligibility if entry.eligible)
        outcome = StrategyRouterOutcome.ROUTED if eligible_families else StrategyRouterOutcome.NO_ELIGIBLE_STRATEGY

        return StrategyRouterResult(
            market_evaluation=market_evaluation,
            outcome=outcome,
            eligibility=eligibility,
            eligible_families=eligible_families,
        )


__all__ = ["StrategyRouter"]
