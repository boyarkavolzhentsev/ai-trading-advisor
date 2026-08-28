"""No mutable module-level runtime state anywhere in ``app.onchain``.

Mirrors ``tests/test_news_module_hygiene.py``: every Stage 4E module's only
top-level bindings are functions, classes, modules, or genuinely immutable
constants - never a shared list/dict/set instance that calls could mutate
across each other.
"""

from __future__ import annotations

import inspect
from datetime import datetime
from decimal import Decimal

import pytest

from app.core.models.network_activity_observation import NetworkActivityObservation
from app.onchain import exceptions, history, protocols, provenance
from app.onchain.history import NetworkActivityObservationHistory

MODULES = (exceptions, history, protocols, provenance)


def _is_type_alias(value: object) -> bool:
    """``NetworkActivityKey = tuple[str, str, str, str, datetime]``-style aliases."""
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


def test_no_quality_module_exists_in_onchain_package() -> None:
    """Stage 4E has no lifecycle-inference helper and no computed-feature
    half - unlike Stage 4D, no model here carries a FeatureQuality verdict,
    so there is nothing for a quality module to classify."""
    import pathlib

    import app.onchain as onchain_package

    package_dir = pathlib.Path(inspect.getfile(onchain_package)).parent
    assert not (package_dir / "quality.py").exists()


def test_no_derived_metric_module_exists() -> None:
    import pathlib

    import app.onchain as onchain_package

    package_dir = pathlib.Path(inspect.getfile(onchain_package)).parent
    forbidden_files = ("derived_metric.py", "derived_metrics.py", "metrics.py")
    for filename in forbidden_files:
        assert not (package_dir / filename).exists()


def test_history_instances_are_independent(now: datetime) -> None:
    observation = NetworkActivityObservation(
        provider="glassnode",
        provider_series_id="btc-active-addresses",
        asset="BTC",
        network="bitcoin",
        observation_time=now,
        received_at=now,
        active_addresses=950_000,
    )
    first = NetworkActivityObservationHistory()
    second = NetworkActivityObservationHistory()
    first.append(observation)
    assert len(first) == 1
    assert len(second) == 0
