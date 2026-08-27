"""No mutable module-level runtime state anywhere in ``app.macro``.

Mirrors ``tests/test_flow_analysts_independence.py``'s
``test_no_mutable_module_level_state``: every Stage 4A module's only
top-level bindings are functions, classes, modules, or genuinely immutable
constants - never a shared list/dict/set instance that calls could mutate
across each other.
"""

from __future__ import annotations

import inspect

import pytest

from app.macro import exceptions, history, protocols, provenance, quality

MODULES = (exceptions, history, protocols, provenance, quality)


def _is_type_alias(value: object) -> bool:
    """``EventKey = tuple[str, str, int]``-style structural aliases.

    These are ``types.GenericAlias``/``TypeVar``/``UnionType`` instances at
    runtime, not classes and not plain immutable literals, but they carry no
    mutable state - the same structural role as a ``TypeVar`` in
    ``app.flow_analysts.base`` (excluded from the analogous upstream check by
    that module simply not being parametrized into it).
    """
    return type(value).__module__ in {"typing", "types"}


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_no_mutable_module_level_state(module) -> None:
    forbidden_globals = {
        name: value
        for name, value in vars(module).items()
        if name not in {"annotations"}
        and not name.startswith("_")
        and not inspect.ismodule(value)
        and not inspect.isclass(value)
        and not inspect.isfunction(value)
        and not _is_type_alias(value)
        and not isinstance(value, (str, int, float, tuple, frozenset, type(None)))
    }
    assert forbidden_globals == {}


def test_economic_event_history_instances_are_independent(now) -> None:
    from decimal import Decimal

    from app.core.enums.economic_calendar import EconomicCategory, EconomicEventStatus
    from app.core.models.economic_event import EconomicEvent
    from app.macro.history import EconomicEventHistory

    event = EconomicEvent(
        provider="testcal",
        provider_event_id="cpi-2026-01",
        country="US",
        currency="USD",
        category=EconomicCategory.CPI,
        name="CPI YoY",
        event_time=now,
        received_at=now,
        status=EconomicEventStatus.SCHEDULED,
    )
    first = EconomicEventHistory()
    second = EconomicEventHistory()
    first.append(event)
    assert len(first) == 1
    assert len(second) == 0
