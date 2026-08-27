"""Determinism: identical inputs produce identical, order-independent results."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from app.core.enums.economic_calendar import EconomicCategory, EconomicEventStatus
from app.core.models.economic_event import EconomicEvent
from app.macro.history import EconomicEventHistory
from app.macro.quality import infer_status


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


def test_model_construction_is_deterministic(now: datetime) -> None:
    first = _event(now)
    second = _event(now)
    assert first == second
    assert first.model_dump() == second.model_dump()


def test_infer_status_is_a_pure_function() -> None:
    results = {infer_status(actual_present=True, revision_number=2) for _ in range(50)}
    assert results == {EconomicEventStatus.REVISED}


def test_history_ordering_is_independent_of_insertion_order(now: datetime) -> None:
    events = [
        _event(now + timedelta(hours=offset), provider_event_id=f"evt-{offset}")
        for offset in (3, 1, 4, 0, 2)
    ]

    forward = EconomicEventHistory()
    for event in events:
        forward.append(event)

    backward = EconomicEventHistory()
    for event in reversed(events):
        backward.append(event)

    forward_ids = [e.provider_event_id for e in forward.all_events()]
    backward_ids = [e.provider_event_id for e in backward.all_events()]
    assert forward_ids == backward_ids == ["evt-0", "evt-1", "evt-2", "evt-3", "evt-4"]


def test_history_append_twice_with_same_events_yields_same_state(now: datetime) -> None:
    events = [_event(now, provider_event_id=f"evt-{i}") for i in range(5)]

    first = EconomicEventHistory()
    second = EconomicEventHistory()
    for event in events:
        first.append(event)
        second.append(event)

    assert [e.model_dump() for e in first.all_events()] == [e.model_dump() for e in second.all_events()]


def test_no_wall_clock_or_randomness_used_by_history(now: datetime) -> None:
    import inspect

    source = inspect.getsource(EconomicEventHistory)
    for forbidden in ("datetime.now", "utcnow", "random.", "uuid."):
        assert forbidden not in source
