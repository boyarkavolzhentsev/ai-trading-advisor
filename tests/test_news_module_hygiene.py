"""No mutable module-level runtime state anywhere in ``app.news``.

Mirrors ``tests/test_macro_module_hygiene.py``/``tests/test_rates_module_hygiene.py``:
every Stage 4C module's only top-level bindings are functions, classes,
modules, or genuinely immutable constants - never a shared list/dict/set
instance that calls could mutate across each other.
"""

from __future__ import annotations

import inspect
from datetime import datetime

import pytest

from app.core.models.news_item import NewsItem
from app.news import exceptions, history, protocols, provenance
from app.news.history import NewsItemHistory

MODULES = (exceptions, history, protocols, provenance)


def _is_type_alias(value: object) -> bool:
    """``NewsItemKey = tuple[str, str]``-style structural aliases.

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


def test_no_quality_module_exists_in_news_package() -> None:
    """Stage 4C has no lifecycle-inference helper - news has no
    scheduled/postponed/cancelled state machine to infer, mirroring
    ``app.rates``'s absence of ``quality.py``."""
    import pathlib

    import app.news as news_package

    package_dir = pathlib.Path(inspect.getfile(news_package)).parent
    assert not (package_dir / "quality.py").exists()


def test_news_history_instances_are_independent(now: datetime) -> None:
    item = NewsItem(
        provider="testnews",
        provider_item_id="story-1",
        headline="Central bank holds rates steady",
        published_at=now,
        received_at=now,
    )
    first = NewsItemHistory()
    second = NewsItemHistory()
    first.append(item)
    assert len(first) == 1
    assert len(second) == 0
