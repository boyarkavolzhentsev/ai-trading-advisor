"""Stage 9 implementation must not create any Stage 10 file.

``app/mt5`` and ``app/execution`` must each still contain only their
pre-existing ``__init__.py`` stub - no production or config module of any
kind. ``app/statistics`` (Stage 9's own designated package) is checked
against the exact approved file set instead - mirrors
``tests/test_portfolio_no_stage9_files.py``/``tests/test_risk_gate_no_stage8_files.py``
one stage over.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

_STAGE_10_PLUS_PACKAGES = (
    "app/mt5",
    "app/execution",
)


def test_stage_10_plus_packages_contain_only_init() -> None:
    for package in _STAGE_10_PLUS_PACKAGES:
        package_dir = REPO_ROOT / package
        assert package_dir.is_dir(), f"{package} is expected to already exist as a stub package"
        python_files = sorted(p.name for p in package_dir.glob("*.py"))
        assert python_files == ["__init__.py"], f"{package} contains unexpected files: {python_files}"


def test_no_session_package_exists() -> None:
    """Session Manager lives inside app/statistics (the one package the
    Stage 0 skeleton pre-stubbed for Stage 9's title, "Statistics / Session
    Management") - not a new top-level app/session package."""
    assert not (REPO_ROOT / "app" / "session").exists()


def test_statistics_package_contains_only_approved_files() -> None:
    package_dir = REPO_ROOT / "app" / "statistics"
    python_files = sorted(p.name for p in package_dir.glob("*.py"))
    assert python_files == ["__init__.py", "aggregator.py", "protocols.py", "session.py"]
