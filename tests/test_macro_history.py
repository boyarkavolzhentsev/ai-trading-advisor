"""Bounded, append-only economic-event history (Stage 4A).

``(provider, provider_event_id, revision_number)`` is the *economic-revision*
identity, not a unique ingestion-record identity: the same revision may be
legitimately observed more than once (a ``SCHEDULED`` placeholder, possibly
re-polled with an updated forecast, then its own ``RELEASED`` realization).
Semantic duplicate detection (below) is what keeps an unchanged re-poll from
consuming a new history slot merely because ``received_at`` differs.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from app.core.enums.economic_calendar import EconomicCategory, EconomicEventStatus
from app.core.models.economic_event import EconomicEvent
from app.macro.exceptions import DuplicateEventError, RevisionConflictError
from app.macro.history import DEFAULT_CAPACITY, EconomicEventHistory


def _event(now: datetime, **overrides: object) -> EconomicEvent:
    fields: dict[str, object] = {
        "provider": "testcal",
        "provider_event_id": "cpi-2026-01",
        "country": "US",
        "currency": "USD",
        "category": EconomicCategory.CPI,
        "name": "CPI YoY",
        "event_time": now,
        "received_at": now,
        "status": EconomicEventStatus.SCHEDULED,
    }
    fields.update(overrides)
    return EconomicEvent(**fields)


def test_default_capacity_is_512() -> None:
    assert DEFAULT_CAPACITY == 512
    assert EconomicEventHistory().capacity == 512


def test_capacity_is_configurable() -> None:
    history = EconomicEventHistory(capacity=10)
    assert history.capacity == 10


def test_scheduled_then_released_is_not_a_conflict(now: datetime) -> None:
    scheduled = _event(now)
    released = scheduled.model_copy(
        update={"status": EconomicEventStatus.RELEASED, "actual": Decimal("0"), "publication_time": now}
    )
    history = EconomicEventHistory()
    history.append(scheduled)
    history.append(released)  # must not raise
    assert len(history) == 2
    assert history.latest_revision("testcal", "cpi-2026-01").actual == Decimal("0")


def test_revision_increments_are_appended_as_new_records(now: datetime) -> None:
    released = _event(now, status=EconomicEventStatus.RELEASED, actual=Decimal("0.2"), publication_time=now)
    revised = released.model_copy(update={"status": EconomicEventStatus.REVISED, "actual": Decimal("0.3"), "revision_number": 1})
    history = EconomicEventHistory()
    history.append(released)
    history.append(revised)
    assert len(history) == 2
    assert history.latest_revision("testcal", "cpi-2026-01").revision_number == 1
    assert len(history.revisions_for("testcal", "cpi-2026-01")) == 2


def test_previous_revisions_remain_retrievable(now: datetime) -> None:
    released = _event(now, status=EconomicEventStatus.RELEASED, actual=Decimal("0.2"), publication_time=now)
    revised = released.model_copy(update={"status": EconomicEventStatus.REVISED, "actual": Decimal("0.3"), "revision_number": 1})
    history = EconomicEventHistory()
    history.append(released)
    history.append(revised)
    revisions = history.revisions_for("testcal", "cpi-2026-01")
    assert revisions[0].actual == Decimal("0.2")
    assert revisions[1].actual == Decimal("0.3")


def test_identical_record_appended_twice_raises_duplicate(now: datetime) -> None:
    event = _event(now, status=EconomicEventStatus.RELEASED, actual=Decimal("0.2"), publication_time=now)
    history = EconomicEventHistory()
    history.append(event)
    with pytest.raises(DuplicateEventError):
        history.append(event)
    assert len(history) == 1


def test_same_revision_conflicting_content_raises_conflict(now: datetime) -> None:
    event = _event(now, status=EconomicEventStatus.RELEASED, actual=Decimal("0.2"), publication_time=now)
    conflicting = event.model_copy(update={"actual": Decimal("0.9")})
    history = EconomicEventHistory()
    history.append(event)
    with pytest.raises(RevisionConflictError):
        history.append(conflicting)
    assert len(history) == 1


def test_regression_from_released_to_scheduled_raises_conflict(now: datetime) -> None:
    released = _event(now, status=EconomicEventStatus.RELEASED, actual=Decimal("2.1"), publication_time=now)
    regressed = released.model_copy(update={"status": EconomicEventStatus.SCHEDULED, "actual": None, "publication_time": None})
    history = EconomicEventHistory()
    history.append(released)
    with pytest.raises(RevisionConflictError):
        history.append(regressed)


def test_two_scheduled_forecast_refinements_are_not_a_conflict(now: datetime) -> None:
    first = _event(now, forecast=Decimal("3.0"))
    refined = first.model_copy(update={"forecast": Decimal("3.2")})
    history = EconomicEventHistory()
    history.append(first)
    history.append(refined)  # must not raise
    assert len(history) == 2


def test_bounded_eviction_is_deterministic_oldest_inserted_first(now: datetime) -> None:
    history = EconomicEventHistory(capacity=2)
    e1 = _event(now, provider_event_id="a")
    e2 = _event(now, provider_event_id="b")
    e3 = _event(now, provider_event_id="c")
    history.append(e1)
    history.append(e2)
    history.append(e3)
    assert history.dropped_count == 1
    assert len(history) == 2
    ids = {e.provider_event_id for e in history.all_events()}
    assert ids == {"b", "c"}
    assert history.latest_revision("testcal", "a") is None


def test_dropped_count_accumulates(now: datetime) -> None:
    history = EconomicEventHistory(capacity=1)
    history.append(_event(now, provider_event_id="a"))
    history.append(_event(now, provider_event_id="b"))
    history.append(_event(now, provider_event_id="c"))
    assert history.dropped_count == 2


def test_provider_isolation(now: datetime) -> None:
    history = EconomicEventHistory()
    history.append(_event(now, provider="provider_a"))
    history.append(_event(now, provider="provider_b"))
    assert len(history.by_provider("provider_a")) == 1
    assert len(history.by_provider("provider_b")) == 1
    assert len(history.by_provider("provider_c")) == 0


def test_colliding_provider_event_id_across_different_providers_does_not_collide(now: datetime) -> None:
    history = EconomicEventHistory()
    a = _event(now, provider="provider_a", provider_event_id="shared-id")
    b = _event(now, provider="provider_b", provider_event_id="shared-id", forecast=Decimal("1"))
    history.append(a)
    history.append(b)  # must not raise despite identical provider_event_id
    assert len(history) == 2
    assert history.latest_revision("provider_a", "shared-id") is not None
    assert history.latest_revision("provider_b", "shared-id") is not None


def test_all_events_ordering_is_deterministic_by_event_time(now: datetime) -> None:
    history = EconomicEventHistory()
    later = _event(now + timedelta(hours=1), provider_event_id="later")
    earlier = _event(now, provider_event_id="earlier")
    history.append(later)
    history.append(earlier)
    ordered_ids = [e.provider_event_id for e in history.all_events()]
    assert ordered_ids == ["earlier", "later"]


def test_all_events_ordering_ties_broken_deterministically(now: datetime) -> None:
    history = EconomicEventHistory()
    b = _event(now, provider_event_id="b")
    a = _event(now, provider_event_id="a")
    history.append(b)
    history.append(a)
    ordered_ids = [e.provider_event_id for e in history.all_events()]
    assert ordered_ids == ["a", "b"]


def test_latest_revision_returns_none_when_never_seen() -> None:
    history = EconomicEventHistory()
    assert history.latest_revision("testcal", "unknown") is None


def test_history_is_len_and_iterable_indirectly_via_all_events(now: datetime) -> None:
    history = EconomicEventHistory()
    assert len(history) == 0
    history.append(_event(now))
    assert len(history) == 1


# --- Semantic duplicate detection (received_at excluded) --------------------


def test_scheduled_repolled_with_only_received_at_changed_is_duplicate(now: datetime) -> None:
    history = EconomicEventHistory()
    scheduled = _event(now, forecast=Decimal("3.0"))
    history.append(scheduled)

    repoll = scheduled.model_copy(update={"received_at": now + timedelta(minutes=30)})
    with pytest.raises(DuplicateEventError):
        history.append(repoll)


def test_rejected_semantic_duplicate_does_not_change_history_length(now: datetime) -> None:
    history = EconomicEventHistory()
    scheduled = _event(now, forecast=Decimal("3.0"))
    history.append(scheduled)

    repoll = scheduled.model_copy(update={"received_at": now + timedelta(minutes=30)})
    with pytest.raises(DuplicateEventError):
        history.append(repoll)
    assert len(history) == 1


def test_rejected_semantic_duplicate_does_not_increment_dropped_count(now: datetime) -> None:
    history = EconomicEventHistory(capacity=5)
    scheduled = _event(now, forecast=Decimal("3.0"))
    history.append(scheduled)

    repoll = scheduled.model_copy(update={"received_at": now + timedelta(minutes=30)})
    with pytest.raises(DuplicateEventError):
        history.append(repoll)
    assert history.dropped_count == 0


def test_released_repolled_with_only_received_at_changed_is_duplicate(now: datetime) -> None:
    history = EconomicEventHistory()
    released = _event(now, status=EconomicEventStatus.RELEASED, actual=Decimal("0.2"), publication_time=now)
    history.append(released)

    repoll = released.model_copy(update={"received_at": now + timedelta(hours=2)})
    with pytest.raises(DuplicateEventError):
        history.append(repoll)
    assert len(history) == 1


def test_scheduled_with_updated_forecast_is_allowed_and_both_observations_retained(now: datetime) -> None:
    history = EconomicEventHistory()
    first = _event(now, forecast=Decimal("3.0"))
    history.append(first)

    updated = first.model_copy(update={"received_at": now + timedelta(minutes=30), "forecast": Decimal("3.2")})
    history.append(updated)  # must not raise

    assert len(history) == 2
    revisions = history.revisions_for("testcal", "cpi-2026-01")
    assert [r.forecast for r in revisions] == [Decimal("3.0"), Decimal("3.2")]


def test_scheduled_to_released_at_revision_zero_is_allowed(now: datetime) -> None:
    history = EconomicEventHistory()
    scheduled = _event(now, forecast=Decimal("3.0"))
    history.append(scheduled)

    released = scheduled.model_copy(
        update={
            "received_at": now + timedelta(hours=1),
            "status": EconomicEventStatus.RELEASED,
            "actual": Decimal("0"),
            "publication_time": now + timedelta(hours=1),
        }
    )
    history.append(released)  # must not raise
    assert len(history) == 2


def test_latest_revision_after_scheduled_to_released_returns_released_observation(now: datetime) -> None:
    history = EconomicEventHistory()
    scheduled = _event(now, forecast=Decimal("3.0"))
    history.append(scheduled)

    released = scheduled.model_copy(
        update={
            "received_at": now + timedelta(hours=1),
            "status": EconomicEventStatus.RELEASED,
            "actual": Decimal("0"),
            "publication_time": now + timedelta(hours=1),
        }
    )
    history.append(released)

    latest = history.latest_revision("testcal", "cpi-2026-01")
    assert latest.status is EconomicEventStatus.RELEASED
    assert latest.actual == Decimal("0")


def test_released_revision_zero_to_revised_revision_one_is_allowed(now: datetime) -> None:
    history = EconomicEventHistory()
    released = _event(now, status=EconomicEventStatus.RELEASED, actual=Decimal("0.2"), publication_time=now)
    history.append(released)

    revised = released.model_copy(
        update={
            "received_at": now + timedelta(days=30),
            "status": EconomicEventStatus.REVISED,
            "actual": Decimal("0.3"),
            "revision_number": 1,
        }
    )
    history.append(revised)  # must not raise
    assert len(history) == 2


def test_latest_revision_returns_revision_one_after_it_arrives(now: datetime) -> None:
    history = EconomicEventHistory()
    released = _event(now, status=EconomicEventStatus.RELEASED, actual=Decimal("0.2"), publication_time=now)
    history.append(released)

    revised = released.model_copy(
        update={
            "received_at": now + timedelta(days=30),
            "status": EconomicEventStatus.REVISED,
            "actual": Decimal("0.3"),
            "revision_number": 1,
        }
    )
    history.append(revised)

    latest = history.latest_revision("testcal", "cpi-2026-01")
    assert latest.revision_number == 1
    assert latest.actual == Decimal("0.3")


def test_same_revision_settled_actual_changed_raises_conflict(now: datetime) -> None:
    history = EconomicEventHistory()
    released = _event(now, status=EconomicEventStatus.RELEASED, actual=Decimal("0.2"), publication_time=now)
    history.append(released)

    conflicting = released.model_copy(update={"received_at": now + timedelta(hours=1), "actual": Decimal("9.9")})
    with pytest.raises(RevisionConflictError):
        history.append(conflicting)
    assert len(history) == 1


def test_settled_to_unsettled_regression_raises_conflict(now: datetime) -> None:
    history = EconomicEventHistory()
    released = _event(now, status=EconomicEventStatus.RELEASED, actual=Decimal("0.2"), publication_time=now)
    history.append(released)

    regressed = released.model_copy(
        update={"received_at": now + timedelta(hours=1), "status": EconomicEventStatus.SCHEDULED, "actual": None, "publication_time": None}
    )
    with pytest.raises(RevisionConflictError):
        history.append(regressed)
    assert len(history) == 1


def test_regression_is_rejected_even_when_content_matches_an_earlier_unsettled_observation(now: datetime) -> None:
    """A settled record must block regression for its key even if the
    reverted content happens to be byte-identical to an *earlier*, still
    unsettled observation of the same key - regression detection must not
    depend on which existing observation the loop happens to compare first.
    """
    history = EconomicEventHistory()
    scheduled = _event(now, forecast=Decimal("3.0"))
    history.append(scheduled)

    released = scheduled.model_copy(
        update={
            "received_at": now + timedelta(hours=1),
            "status": EconomicEventStatus.RELEASED,
            "actual": Decimal("0"),
            "publication_time": now + timedelta(hours=1),
        }
    )
    history.append(released)

    # byte-identical to `scheduled` except received_at
    regressed = scheduled.model_copy(update={"received_at": now + timedelta(hours=2)})
    with pytest.raises(RevisionConflictError):
        history.append(regressed)
    assert len(history) == 2


def test_provider_isolation_remains_intact_with_semantic_duplicate_detection(now: datetime) -> None:
    history = EconomicEventHistory()
    a = _event(now, provider="provider_a")
    b = a.model_copy(update={"provider": "provider_b", "received_at": now})
    history.append(a)
    history.append(b)  # same fingerprint fields except `provider` itself differs -> not a duplicate
    assert len(history.by_provider("provider_a")) == 1
    assert len(history.by_provider("provider_b")) == 1


def test_bounded_eviction_remains_deterministic_after_semantic_fix(now: datetime) -> None:
    history = EconomicEventHistory(capacity=2)
    history.append(_event(now, provider_event_id="a"))
    history.append(_event(now, provider_event_id="b"))
    history.append(_event(now, provider_event_id="c"))
    assert history.dropped_count == 1
    assert {e.provider_event_id for e in history.all_events()} == {"b", "c"}


def test_equivalent_input_sequence_produces_identical_query_results(now: datetime) -> None:
    def build() -> EconomicEventHistory:
        history = EconomicEventHistory()
        scheduled = _event(now, forecast=Decimal("3.0"))
        history.append(scheduled)
        released = scheduled.model_copy(
            update={
                "received_at": now + timedelta(hours=1),
                "status": EconomicEventStatus.RELEASED,
                "actual": Decimal("0"),
                "publication_time": now + timedelta(hours=1),
            }
        )
        history.append(released)
        revised = released.model_copy(
            update={
                "received_at": now + timedelta(days=1),
                "status": EconomicEventStatus.REVISED,
                "actual": Decimal("0.1"),
                "revision_number": 1,
            }
        )
        history.append(revised)
        return history

    first = build()
    second = build()
    assert [e.model_dump() for e in first.all_events()] == [e.model_dump() for e in second.all_events()]
    assert first.latest_revision("testcal", "cpi-2026-01").model_dump() == second.latest_revision(
        "testcal", "cpi-2026-01"
    ).model_dump()
