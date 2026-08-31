"""Stage 6C implementation must not create any Stage 9/10 file.

``app/risk`` and ``app/money_management`` are Stage 7's own designated
packages, ``app/diversification`` is Stage 8's own designated package, and
``app/statistics`` is Stage 9's own designated package (all approved and
implemented in later turns than this test's own Stage 6C authorship - see
``tests/risk_gate_support.py``/``tests/test_risk_gate_*.py``,
``tests/portfolio_support.py``/``tests/test_portfolio_*.py``, and
``tests/session_support.py``/``tests/test_session_gate_*.py``/
``tests/test_statistics_*.py`` for their own coverage) and are therefore no
longer checked here. ``app/mt5`` and ``app/execution`` must still contain
only their pre-existing ``__init__.py`` stub - no production or config
module of any kind.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

_STAGE_9_PLUS_PACKAGES = (
    "app/mt5",
    "app/execution",
)


def test_stage_9_plus_packages_contain_only_init() -> None:
    for package in _STAGE_9_PLUS_PACKAGES:
        package_dir = REPO_ROOT / package
        assert package_dir.is_dir(), f"{package} is expected to already exist as a stub package"
        python_files = sorted(p.name for p in package_dir.glob("*.py"))
        assert python_files == ["__init__.py"], f"{package} contains unexpected files: {python_files}"
