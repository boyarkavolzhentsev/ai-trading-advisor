"""Determinism: identical inputs produce identical, order-independent results."""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta
from decimal import Decimal

from app.core.enums.rates import GovernmentYieldType, SeriesUnit
from app.core.models.government_yield_observation import GovernmentYieldObservation
from app.core.models.tenor import Tenor
from app.rates.history import GovernmentYieldObservationHistory, PolicyRateObservationHistory


def _obs(now: datetime, **overrides: object) -> GovernmentYieldObservation:
    fields: dict[str, object] = {
        "provider": "testrates",
        "provider_series_id": "us-10y-nominal",
        "country": "US",
        "currency": "USD",
        "yield_type": GovernmentYieldType.NOMINAL,
        "tenor": Tenor.of_years(10),
        "value": Decimal("4.10"),
        "unit": SeriesUnit.PERCENT,
        "observation_time": now,
        "received_at": now,
    }
    fields.update(overrides)
    return GovernmentYieldObservation(**fields)


def test_model_construction_is_deterministic(now: datetime) -> None:
    first = _obs(now)
    second = _obs(now)
    assert first == second
    assert first.model_dump() == second.model_dump()


def test_tenor_construction_is_deterministic() -> None:
    results = {Tenor.of_months(24) for _ in range(50)}
    assert results == {Tenor.of_years(2)}


def test_history_ordering_is_independent_of_insertion_order(now: datetime) -> None:
    observations = [
        _obs(now + timedelta(hours=offset), provider_series_id=f"series-{offset}") for offset in (3, 1, 4, 0, 2)
    ]

    forward = GovernmentYieldObservationHistory()
    for obs in observations:
        forward.append(obs)

    backward = GovernmentYieldObservationHistory()
    for obs in reversed(observations):
        backward.append(obs)

    forward_ids = [o.provider_series_id for o in forward.all_observations()]
    backward_ids = [o.provider_series_id for o in backward.all_observations()]
    assert forward_ids == backward_ids == [f"series-{i}" for i in (0, 1, 2, 3, 4)]


def test_history_append_twice_with_same_observations_yields_same_state(now: datetime) -> None:
    observations = [_obs(now, provider_series_id=f"series-{i}") for i in range(5)]

    first = GovernmentYieldObservationHistory()
    second = GovernmentYieldObservationHistory()
    for obs in observations:
        first.append(obs)
        second.append(obs)

    assert [o.model_dump() for o in first.all_observations()] == [o.model_dump() for o in second.all_observations()]


def test_no_wall_clock_or_randomness_used_by_history() -> None:
    for cls in (GovernmentYieldObservationHistory, PolicyRateObservationHistory):
        source = inspect.getsource(cls)
        for forbidden in ("datetime.now", "utcnow", "random.", "uuid."):
            assert forbidden not in source
