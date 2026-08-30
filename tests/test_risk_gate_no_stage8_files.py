"""Stage 7 implementation must not create any Stage 8/9/10 file.

``app/diversification``, ``app/mt5``, ``app/execution`` and
``app/statistics`` must each still contain only their pre-existing
``__init__.py`` stub - no production or config module of any kind. No
``app/portfolio`` package exists at all.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

_STAGE_8_PLUS_PACKAGES = (
    "app/diversification",
    "app/mt5",
    "app/execution",
    "app/statistics",
)


def test_stage_8_plus_packages_contain_only_init() -> None:
    for package in _STAGE_8_PLUS_PACKAGES:
        package_dir = REPO_ROOT / package
        assert package_dir.is_dir(), f"{package} is expected to already exist as a stub package"
        python_files = sorted(p.name for p in package_dir.glob("*.py"))
        assert python_files == ["__init__.py"], f"{package} contains unexpected files: {python_files}"


def test_no_portfolio_package_exists() -> None:
    assert not (REPO_ROOT / "app" / "portfolio").exists()
