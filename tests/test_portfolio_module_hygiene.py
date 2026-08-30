"""No mutable module-level runtime state anywhere in ``app.diversification``.

Mirrors ``tests/test_risk_gate_module_hygiene.py`` one stage over.
"""

from __future__ import annotations

import inspect

import pytest

from app.diversification import protocols, supervisor

MODULES = (supervisor, protocols)


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
