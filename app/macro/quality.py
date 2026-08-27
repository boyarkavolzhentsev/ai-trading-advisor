"""Stage 4A lifecycle-inference helper - judge, never repair.

Mirrors ``app.flow.quality``'s stance: the helper here only classifies
already-known inputs; it never fills in, guesses, or repairs a missing fact.
Lifecycle (``EconomicEventStatus``) and data quality (``DataQuality``) are
kept strictly separate - see the Stage 4A design report - so nothing here
returns a quality verdict, and ``FeatureQuality``/``DataQuality`` are never
redefined here. A raw-fetch verdict about a batch of events should be built
with the existing ``app.core.models.data_quality.DataQuality``, unchanged.
"""

from __future__ import annotations

from app.core.enums.economic_calendar import EconomicEventStatus


def infer_status(
    *,
    actual_present: bool,
    revision_number: int,
    provider_postponed: bool = False,
    provider_cancelled: bool = False,
) -> EconomicEventStatus:
    """Derive an ``EconomicEventStatus`` when a provider gives no explicit lifecycle flag.

    ``provider_postponed``/``provider_cancelled`` must come from an explicit
    provider signal - never inferred from a late ``event_time``. They take
    priority over ``actual_present`` because neither postponement nor
    cancellation is derivable from field presence alone: a postponed event
    and a still-``SCHEDULED`` event are otherwise indistinguishable (both
    have no ``actual``).
    """
    if provider_cancelled:
        return EconomicEventStatus.CANCELLED
    if provider_postponed:
        return EconomicEventStatus.POSTPONED
    if not actual_present:
        return EconomicEventStatus.SCHEDULED
    return EconomicEventStatus.REVISED if revision_number > 0 else EconomicEventStatus.RELEASED


__all__ = ["infer_status"]
