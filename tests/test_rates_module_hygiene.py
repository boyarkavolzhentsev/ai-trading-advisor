"""No mutable module-level runtime state anywhere in ``app.rates``.

Mirrors ``tests/test_macro_module_hygiene.py``: every Stage 4B module's only
top-level bindings are functions, classes, modules, or genuinely immutable
constants - never a shared list/dict/set instance that calls could mutate
across each other.
"""

from __future__ import annotations

import inspect
from datetime import datetime
from decimal import Decimal

import pytest

from app.core.enums.economic_calendar import CentralBank
from app.core.enums.rates import GovernmentYieldType, PolicyRateKind, SeriesUnit
from app.core.models.government_yield_observation import GovernmentYieldObservation
from app.core.models.policy_rate_observation import PolicyRateObservation
from app.core.models.tenor import Tenor
from app.rates import exceptions, history, protocols, provenance
from app.rates.history import GovernmentYieldObservationHistory, PolicyRateObservationHistory

MODULES = (exceptions, history, protocols, provenance)


def _is_type_alias(value: object) -> bool:
    """``PolicyRateKey = tuple[str, str, datetime, int]``-style structural aliases.

    These are ``types.GenericAlias``/``TypeVar``/``UnionType`` instances at
    runtime, not classes and not plain immutable literals, but they carry no
    mutable state.
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


def test_no_quality_module_exists_in_rates_package() -> None:
    """Stage 4B has no lifecycle-inference helper - a continuous time series
    has no scheduled/postponed/cancelled state machine to infer, unlike
    Stage 4A's ``app.macro.quality``."""
    import pathlib

    import app.rates as rates_package

    package_dir = pathlib.Path(inspect.getfile(rates_package)).parent
    assert not (package_dir / "quality.py").exists()


def test_policy_rate_history_instances_are_independent(now: datetime) -> None:
    observation = PolicyRateObservation(
        provider="testrates",
        provider_series_id="fed-target-lower",
        central_bank=CentralBank.FED,
        currency="USD",
        rate_kind=PolicyRateKind.TARGET_LOWER,
        value=Decimal("4.25"),
        unit=SeriesUnit.PERCENT,
        observation_time=now,
        received_at=now,
    )
    first = PolicyRateObservationHistory()
    second = PolicyRateObservationHistory()
    first.append(observation)
    assert len(first) == 1
    assert len(second) == 0


def test_government_yield_history_instances_are_independent(now: datetime) -> None:
    observation = GovernmentYieldObservation(
        provider="testrates",
        provider_series_id="us-10y-nominal",
        country="US",
        currency="USD",
        yield_type=GovernmentYieldType.NOMINAL,
        tenor=Tenor.of_years(10),
        value=Decimal("4.10"),
        unit=SeriesUnit.PERCENT,
        observation_time=now,
        received_at=now,
    )
    first = GovernmentYieldObservationHistory()
    second = GovernmentYieldObservationHistory()
    first.append(observation)
    assert len(first) == 1
    assert len(second) == 0
