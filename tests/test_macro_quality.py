"""``app.macro.quality.infer_status`` - pure lifecycle inference, no repair."""

from __future__ import annotations

from app.core.enums.economic_calendar import EconomicEventStatus
from app.macro.quality import infer_status


def test_no_actual_infers_scheduled() -> None:
    assert infer_status(actual_present=False, revision_number=0) is EconomicEventStatus.SCHEDULED


def test_actual_present_zero_revision_infers_released() -> None:
    assert infer_status(actual_present=True, revision_number=0) is EconomicEventStatus.RELEASED


def test_actual_present_positive_revision_infers_revised() -> None:
    assert infer_status(actual_present=True, revision_number=1) is EconomicEventStatus.REVISED


def test_explicit_provider_postponed_wins_over_actual_presence() -> None:
    assert (
        infer_status(actual_present=False, revision_number=0, provider_postponed=True)
        is EconomicEventStatus.POSTPONED
    )


def test_explicit_provider_cancelled_wins_over_postponed_and_actual() -> None:
    assert (
        infer_status(
            actual_present=True,
            revision_number=2,
            provider_postponed=True,
            provider_cancelled=True,
        )
        is EconomicEventStatus.CANCELLED
    )


def test_no_arbitrary_staleness_threshold_parameter_exists() -> None:
    """``infer_status`` must never accept a staleness/age cutoff - that
    vocabulary belongs to ``DataQuality``, one layer up, not to lifecycle."""
    import inspect

    signature = inspect.signature(infer_status)
    forbidden = {"stale", "staleness", "age_seconds", "max_age", "horizon"}
    assert forbidden.isdisjoint(signature.parameters)
