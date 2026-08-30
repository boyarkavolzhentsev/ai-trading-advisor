"""``app.money_management.sizing`` must remain a narrow pure calculator: no
Policy/Judge/Router import, no account-state/config import, no broker
rounding, no I/O, no portfolio allocation."""

from __future__ import annotations

import ast
import inspect
from decimal import Decimal
from pathlib import Path

from app.money_management import sizing
from app.money_management.sizing import calculate_recommended_units


def test_sizing_module_imports_only_decimal() -> None:
    path = Path(inspect.getfile(sizing))
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    assert imports == {"__future__", "decimal"}


def test_sizing_module_has_no_rounding_call() -> None:
    path = Path(inspect.getfile(sizing))
    source = path.read_text(encoding="utf-8")
    for forbidden in ("round(", "quantize", "ROUND_"):
        assert forbidden not in source, f"sizing.py contains a forbidden rounding construct: {forbidden!r}"


def test_calculate_recommended_units_exact_division() -> None:
    result = calculate_recommended_units(max_individual_risk=Decimal("500"), risk_per_unit=Decimal("7"))
    assert result == Decimal("500") / Decimal("7")


def test_calculate_recommended_units_returns_decimal() -> None:
    result = calculate_recommended_units(max_individual_risk=Decimal("500"), risk_per_unit=Decimal("10"))
    assert isinstance(result, Decimal)
    assert result == Decimal("50")
