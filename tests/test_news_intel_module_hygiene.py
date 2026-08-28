"""No mutable module-level runtime state anywhere in ``app.news_intel``.

Mirrors ``tests/test_news_module_hygiene.py``: every Stage 4D module's only
top-level bindings are functions, classes, modules, or genuinely immutable
constants - never a shared list/dict/set instance that calls could mutate
across each other.
"""

from __future__ import annotations

import inspect
from datetime import datetime

import pytest

from app.core.models.news_sentiment_observation import NewsSentimentObservation
from app.news_intel import exceptions, provenance, relevance, sentiment_history, sentiment_protocol
from app.news_intel.sentiment_history import NewsSentimentObservationHistory

MODULES = (exceptions, provenance, relevance, sentiment_history, sentiment_protocol)


def _is_type_alias(value: object) -> bool:
    """``NewsSentimentKey = tuple[str, str, str, str | None]``-style structural aliases."""
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


def test_relevance_module_defines_no_exception_class() -> None:
    """Deliberate asymmetry: relevance has no failure mode of its own -
    no exception class should be defined in that module."""
    import inspect as inspect_module

    defined_classes = [
        obj
        for _, obj in vars(relevance).items()
        if inspect_module.isclass(obj) and issubclass(obj, BaseException)
    ]
    assert defined_classes == []


def test_relevance_module_defines_no_protocol() -> None:
    """Deliberate asymmetry: relevance has no independently-fetched data -
    no provider Protocol should be defined in that module.

    Checked via actual imports (not source-text scanning) since the
    module's own docstring legitimately discusses "no protocol" in prose.
    """
    import ast

    tree = ast.parse(inspect.getsource(relevance))
    imported_names = {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert "Protocol" not in imported_names
    assert "runtime_checkable" not in imported_names


def test_no_relevance_history_module_exists() -> None:
    import pathlib

    import app.news_intel as news_intel_package

    package_dir = pathlib.Path(inspect.getfile(news_intel_package)).parent
    assert not (package_dir / "relevance_history.py").exists()


def test_sentiment_history_instances_are_independent(now: datetime) -> None:
    observation = NewsSentimentObservation(
        provider="sentvendor",
        source_provider="testnews",
        source_provider_item_id="story-1",
        source_received_at=now,
        published_at=now,
        received_at=now,
        sentiment_label="positive",
    )
    first = NewsSentimentObservationHistory()
    second = NewsSentimentObservationHistory()
    first.append(observation)
    assert len(first) == 1
    assert len(second) == 0
