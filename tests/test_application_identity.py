"""``app.application.identity`` tests: caller-owned logical_cycle_id policy,
deterministic trade_id derivation, filesystem-safety charset."""

from __future__ import annotations

import ast
import inspect

import pytest

import app.application.identity as identity_module
from app.application.advisory_service import ApplicationAdvisoryService
from app.application.errors import ApplicationInputError
from app.application.identity import derive_trade_id, derive_trade_ids, validate_logical_cycle_id
from app.core.enums.strategy_router import StrategyFamily

VALID_ID = "cycle-123_ABC"


def test_derive_trade_id_deterministic() -> None:
    assert derive_trade_id(VALID_ID, StrategyFamily.BREAKOUT) == derive_trade_id(VALID_ID, StrategyFamily.BREAKOUT)


def test_derive_trade_id_exact_format() -> None:
    assert derive_trade_id("abc", StrategyFamily.TREND_FOLLOWING) == "abc__TREND_FOLLOWING"


def test_same_logical_cycle_id_same_mapping() -> None:
    assert derive_trade_ids(VALID_ID) == derive_trade_ids(VALID_ID)


def test_different_logical_cycle_id_different_mapping() -> None:
    mapping_a = derive_trade_ids("cycle-a")
    mapping_b = derive_trade_ids("cycle-b")
    assert mapping_a != mapping_b
    for family in StrategyFamily:
        assert mapping_a[family] != mapping_b[family]


def test_every_strategy_family_covered() -> None:
    mapping = derive_trade_ids(VALID_ID)
    assert set(mapping.keys()) == set(StrategyFamily)


@pytest.mark.parametrize("family", list(StrategyFamily))
def test_derived_trade_id_is_windows_safe(family: StrategyFamily) -> None:
    trade_id = derive_trade_id(VALID_ID, family)
    assert ":" not in trade_id
    assert "/" not in trade_id
    assert "\\" not in trade_id
    assert "." not in trade_id


def test_valid_id_length_bounds_accepted() -> None:
    validate_logical_cycle_id("a")
    validate_logical_cycle_id("a" * 128)


@pytest.mark.parametrize(
    "invalid",
    [
        "",
        "has:colon",
        "has/slash",
        "has\\backslash",
        "has.dot",
        "has space",
        "has\ttab",
        "héllo",
        "a" * 129,
        "..",
        "../etc",
    ],
)
def test_invalid_logical_cycle_id_rejected(invalid: str) -> None:
    with pytest.raises(ApplicationInputError):
        validate_logical_cycle_id(invalid)


def test_no_forbidden_identity_generation_in_identity_module() -> None:
    """AST-based (not substring) so this cannot false-positive on an
    explanatory docstring/comment mentioning these names in prose - mirrors
    ``tests/test_production_advisory_composer.py::test_composer_module_never_generates_ids``."""
    tree = ast.parse(inspect.getsource(identity_module))
    forbidden_names = {"uuid4", "uuid", "random", "secrets", "hash"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not any(alias.name in forbidden_names for alias in node.names)
        if isinstance(node, ast.ImportFrom) and node.module:
            assert node.module not in forbidden_names
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in forbidden_names


def test_no_forbidden_identity_generation_in_advisory_service_module() -> None:
    import app.application.advisory_service as service_module

    tree = ast.parse(inspect.getsource(service_module))
    forbidden_names = {"uuid4", "uuid", "random", "secrets"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not any(alias.name in forbidden_names for alias in node.names)
        if isinstance(node, ast.ImportFrom) and node.module:
            assert node.module not in forbidden_names
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in forbidden_names


def test_no_generated_id_convenience_method_exists() -> None:
    assert not hasattr(ApplicationAdvisoryService, "create_advisory_with_generated_id")
    assert not hasattr(ApplicationAdvisoryService, "get_latest_advisory")
