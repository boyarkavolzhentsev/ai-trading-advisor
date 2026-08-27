"""``EconomicCalendarProvider`` protocol shape: sync, runtime_checkable, narrow."""

from __future__ import annotations

import inspect
from collections.abc import Sequence
from datetime import datetime

from app.core.enums.economic_calendar import EconomicCategory
from app.core.models.economic_event import EconomicEvent
from app.macro.protocols import DEFAULT_EVENT_LIMIT, EconomicCalendarProvider


class _FakeEconomicCalendarProvider:
    """Minimal fixture satisfying ``EconomicCalendarProvider`` structurally."""

    def get_events(
        self,
        start: datetime,
        end: datetime,
        *,
        countries: Sequence[str] | None = None,
        categories: Sequence[EconomicCategory] | None = None,
        limit: int = DEFAULT_EVENT_LIMIT,
    ) -> list[EconomicEvent]:
        return []


class _NotAProvider:
    pass


def test_fake_provider_satisfies_protocol_structurally() -> None:
    assert isinstance(_FakeEconomicCalendarProvider(), EconomicCalendarProvider)


def test_unrelated_object_does_not_satisfy_protocol() -> None:
    assert not isinstance(_NotAProvider(), EconomicCalendarProvider)


def test_get_events_is_synchronous_not_a_coroutine_function() -> None:
    assert not inspect.iscoroutinefunction(EconomicCalendarProvider.get_events)
    assert not inspect.iscoroutinefunction(_FakeEconomicCalendarProvider.get_events)


def test_default_event_limit_is_a_positive_int() -> None:
    assert isinstance(DEFAULT_EVENT_LIMIT, int)
    assert DEFAULT_EVENT_LIMIT > 0


def test_protocol_has_exactly_one_capability_method() -> None:
    public_methods = [
        name
        for name, value in vars(EconomicCalendarProvider).items()
        if not name.startswith("_") and callable(value)
    ]
    assert public_methods == ["get_events"]
