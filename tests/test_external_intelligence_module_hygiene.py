"""No mutable module-level runtime state anywhere in ``app.external_intelligence_analysts``."""

from __future__ import annotations

import inspect

import pytest

from app.external_intelligence_analysts import base, config, macro_event, news_sentiment, on_chain, protocols, rates_yield

MODULES = (base, config, protocols, macro_event, rates_yield, news_sentiment, on_chain)


def _is_type_alias(value: object) -> bool:
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


def test_relationship_map_no_longer_exists() -> None:
    """``_RELATIONSHIP_MAP`` was removed: no factually-grounded deterministic
    relationship between network-activity direction and exchange-flow
    direction exists in the Stage 4A-4E foundations, so no sign-pairing
    table maps them together - see ``on_chain.py``'s module docstring."""
    assert not hasattr(on_chain, "_RELATIONSHIP_MAP")
