"""No mutable module-level runtime state anywhere in ``app.statistics``; no
pseudo-confidence/ranking/voting vocabulary; frozen/extra-forbid model
config; no ``app.mt5``/``app.execution`` import.

Mirrors ``tests/test_portfolio_module_hygiene.py`` one stage over.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from app.core.models.session_result import SessionFamilyResult, StrategySessionResult
from app.statistics import aggregator, protocols, session

MODULES = (session, aggregator, protocols)

FORBIDDEN_VOCABULARY = (
    "confidence",
    "ranking",
    "rank",
    "score",
    "weight",
    "vote",
    "winner",
    "preferred",
)


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


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_no_pseudo_confidence_ranking_or_voting_identifier(module) -> None:
    """Checks actual identifiers (function/variable/argument/attribute
    names) only - never docstring prose, which legitimately *documents* this
    prohibition (see each module's own module-level docstring)."""
    path = Path(inspect.getfile(module))
    tree = ast.parse(path.read_text(encoding="utf-8"))
    identifiers: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            identifiers.add(node.name)
        elif isinstance(node, ast.Name):
            identifiers.add(node.id)
        elif isinstance(node, ast.arg):
            identifiers.add(node.arg)
        elif isinstance(node, ast.Attribute):
            identifiers.add(node.attr)

    offending = {
        identifier for identifier in identifiers for word in FORBIDDEN_VOCABULARY if word in identifier.lower()
    }
    assert offending == set(), f"{module.__name__} defines/references forbidden identifier(s): {offending}"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__)
def test_no_mt5_or_execution_import(module) -> None:
    path = Path(inspect.getfile(module))
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    offending = {name for name in imports if name.startswith(("app.mt5", "app.execution"))}
    assert offending == set()


def test_session_family_result_frozen_and_extra_forbid() -> None:
    config = SessionFamilyResult.model_config
    assert config.get("frozen") is True
    assert config.get("extra") == "forbid"


def test_strategy_session_result_frozen_and_extra_forbid() -> None:
    config = StrategySessionResult.model_config
    assert config.get("frozen") is True
    assert config.get("extra") == "forbid"
