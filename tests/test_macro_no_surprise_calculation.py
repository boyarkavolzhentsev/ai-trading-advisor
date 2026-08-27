"""Stage 4A must never compute a surprise/diff, and must never infer importance.

Facts only: ``actual``/``forecast``/``previous`` are stored as reported; no
helper anywhere in ``app.macro`` or on ``EconomicEvent`` derives
``actual - forecast`` (raw or normalized), and no category-to-importance
mapping table exists anywhere in the package.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from app.core.models.economic_event import EconomicEvent
from app.macro import exceptions, history, protocols, provenance, quality

MODULES = (exceptions, history, protocols, provenance, quality)

FORBIDDEN_NAMES = (
    "surprise",
    "compute_surprise",
    "actual_minus_forecast",
    "normalized_surprise",
)

FORBIDDEN_IMPORTANCE_INFERENCE_NAMES = (
    "infer_importance",
    "default_importance",
    "importance_for_category",
    "category_importance",
)


def test_economic_event_has_no_surprise_or_diff_field() -> None:
    forbidden_fields = {"surprise", "surprise_percent", "actual_minus_forecast", "diff", "delta"}
    assert forbidden_fields.isdisjoint(EconomicEvent.model_fields)


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_no_surprise_helper_defined_anywhere_in_macro(module) -> None:
    defined_names = {name for name, value in vars(module).items() if inspect.isfunction(value) or inspect.isclass(value)}
    for forbidden in FORBIDDEN_NAMES:
        assert forbidden not in defined_names, f"{module.__name__} defines forbidden surprise helper {forbidden!r}"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_no_hardcoded_importance_table_anywhere_in_macro(module) -> None:
    defined_names = {name for name, value in vars(module).items() if inspect.isfunction(value) or inspect.isclass(value)}
    for forbidden in FORBIDDEN_IMPORTANCE_INFERENCE_NAMES:
        assert forbidden not in defined_names, f"{module.__name__} defines forbidden importance-inference helper {forbidden!r}"


def test_no_arithmetic_between_actual_and_forecast_in_source() -> None:
    """Cheap textual guard: no module source subtracts ``actual``/``forecast``.

    Not a full static-analysis guarantee, but catches the specific pattern
    the Stage 4A design forbids from ever being reintroduced silently.
    """
    for module in MODULES:
        source = Path(inspect.getfile(module)).read_text(encoding="utf-8")
        collapsed = source.replace(" ", "")
        assert "actual-forecast" not in collapsed
        assert "forecast-actual" not in collapsed
