"""MT5 Price Authority Stage C removal-proof audit.

Repository-wide, working-tree-source-only (never git history) proof that
every cross-venue price-basis reconciliation construct this stage removes
has zero remaining occurrences in production code (``app/``):

    binance_reference_price
    max_price_basis_divergence_percent / MAX_PRICE_BASIS_DIVERGENCE_PERCENT
    PRICE_BASIS_DIVERGENCE
    binance_structural_stop
    m15_last_closed_close
    market_data_symbol

Scans ``app/`` only (never ``tests/``): this module and its sibling Stage C
tests are themselves allowed - and in some cases required - to name these
identifiers in prose explaining what was removed and why (mirrors every
prior stage's own removal-proof convention, e.g.
``tests/test_technical_no_mt5_provider_coupling.py`` scanning only
``app/technical`` for ``MT5OHLCVProvider``, never scanning itself).
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
APP_ROOT = REPO_ROOT / "app"

_REMOVED_IDENTIFIERS = (
    "binance_reference_price",
    "max_price_basis_divergence_percent",
    "MAX_PRICE_BASIS_DIVERGENCE_PERCENT",
    "PRICE_BASIS_DIVERGENCE",
    "binance_structural_stop",
    "m15_last_closed_close",
    "market_data_symbol",
)


def _all_app_source_files() -> list[Path]:
    return sorted(APP_ROOT.rglob("*.py"))


def test_app_source_contains_zero_occurrences_of_every_removed_identifier() -> None:
    offenders: list[str] = []
    for path in _all_app_source_files():
        source = path.read_text(encoding="utf-8")
        for identifier in _REMOVED_IDENTIFIERS:
            if identifier in source:
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {identifier}")
    assert not offenders, "removed MT5 Price Authority Stage C identifiers still referenced:\n" + "\n".join(offenders)


def test_at_least_one_app_source_file_was_scanned() -> None:
    """Guards against a silently-empty scan (e.g. a wrong path) producing a
    vacuously-true removal proof."""
    assert len(_all_app_source_files()) > 100


def test_setup_construction_module_has_no_translation_helper() -> None:
    """The specific function this stage deletes - proven by name, not just
    by its old call-site kwargs."""
    import app.decision.setup_construction as module

    assert not hasattr(module, "_translate_binance_distance_to_mt5_stop")


def test_technical_production_result_has_no_reference_price_field() -> None:
    from app.technical.production import TechnicalProductionResult

    assert "m15_last_closed_close" not in TechnicalProductionResult.__dataclass_fields__


def test_production_advisory_config_has_no_basis_divergence_field() -> None:
    from app.production_advisory.config import ProductionAdvisoryConfig

    assert "max_price_basis_divergence_percent" not in ProductionAdvisoryConfig.model_fields


def test_advisory_response_and_cycle_result_have_no_market_data_symbol_field() -> None:
    from app.application.dto import AdvisoryResponse
    from app.production_advisory.result import ProductionAdvisoryCycleResult

    assert "market_data_symbol" not in AdvisoryResponse.model_fields
    assert "market_data_symbol" not in ProductionAdvisoryCycleResult.model_fields
