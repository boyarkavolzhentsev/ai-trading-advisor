"""Stage 10E-adjacent ``MT5RecommendationProvenancePersistence``: typed read
status, atomic write, corruption/unavailable fail-closed, stable trade_id
path behavior, coexistence with Stage 10E's own tracking store, and full
restart round-trips (Final Runtime Integration, Part E corrective design)."""

from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path

import pytest

from app.core.enums.strategy_router import StrategyFamily
from app.core.models.final_recommendation_provenance import FinalRecommendationProvenance
from app.mt5.recommendation_persistence import MT5RecommendationPersistence
from app.mt5.recommendation_provenance_persistence import MT5RecommendationProvenancePersistence
from tests.mt5_matching_support import default_tracked_recommendation


def _provenance(**overrides: object) -> FinalRecommendationProvenance:
    fields: dict[str, object] = {
        "trade_id": "trade-1",
        "family": StrategyFamily.TREND_FOLLOWING,
        "approved_risk_amount": Decimal("120"),
        "account_currency": "DKK",
    }
    fields.update(overrides)
    return FinalRecommendationProvenance(**fields)


@pytest.fixture
def store(tmp_path: Path) -> MT5RecommendationProvenancePersistence:
    return MT5RecommendationProvenancePersistence(tmp_path)


# --- typed read status ---


def test_absent_when_never_written(store: MT5RecommendationProvenancePersistence) -> None:
    status, value = store.read("trade-1")
    assert status == "ABSENT"
    assert value is None


def test_valid_round_trip(store: MT5RecommendationProvenancePersistence) -> None:
    provenance = _provenance()
    assert store.write("trade-1", provenance) is True
    status, value = store.read("trade-1")
    assert status == "VALID"
    assert value == provenance


def test_corrupt_json(store: MT5RecommendationProvenancePersistence, tmp_path: Path) -> None:
    (tmp_path / "trade-1.provenance.json").write_text("{not valid json", encoding="utf-8")
    status, value = store.read("trade-1")
    assert status == "CORRUPT"
    assert value is None


def test_corrupt_schema_mismatch(store: MT5RecommendationProvenancePersistence, tmp_path: Path) -> None:
    (tmp_path / "trade-1.provenance.json").write_text('{"foo": "bar"}', encoding="utf-8")
    status, value = store.read("trade-1")
    assert status == "CORRUPT"
    assert value is None


def test_unavailable_directory_missing(tmp_path: Path) -> None:
    store = MT5RecommendationProvenancePersistence(tmp_path / "does-not-exist")
    status, value = store.read("trade-1")
    assert status == "ABSENT"
    assert value is None


# --- atomic write ---


def test_write_creates_no_stray_tmp_file_on_success(
    store: MT5RecommendationProvenancePersistence, tmp_path: Path
) -> None:
    store.write("trade-1", _provenance())
    assert not (tmp_path / "trade-1.provenance.json.tmp").exists()
    assert (tmp_path / "trade-1.provenance.json").exists()


def test_failed_replace_preserves_existing_valid_file(
    store: MT5RecommendationProvenancePersistence, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = _provenance()
    store.write("trade-1", original)

    def _boom(*args: object, **kwargs: object) -> None:
        raise OSError("simulated disk failure")

    monkeypatch.setattr(os, "replace", _boom)
    updated = _provenance(approved_risk_amount=Decimal("999"))
    ok = store.write("trade-1", updated)
    assert ok is False

    monkeypatch.undo()
    status, value = store.read("trade-1")
    assert status == "VALID"
    assert value == original
    assert not (tmp_path / "trade-1.provenance.json.tmp").exists()


# --- stable trade_id path behavior ---


def test_unsafe_trade_id_with_path_separator_rejected_on_write(store: MT5RecommendationProvenancePersistence) -> None:
    assert store.write("../escape", _provenance()) is False


def test_unsafe_trade_id_with_path_separator_rejected_on_read(store: MT5RecommendationProvenancePersistence) -> None:
    status, value = store.read("nested/path")
    assert status == "UNAVAILABLE"
    assert value is None


def test_empty_trade_id_rejected(store: MT5RecommendationProvenancePersistence) -> None:
    assert store.write("", _provenance()) is False


def test_distinct_trade_ids_do_not_collide(store: MT5RecommendationProvenancePersistence) -> None:
    a = _provenance()
    b = _provenance(approved_risk_amount=Decimal("50"))
    store.write("trade-a", a)
    store.write("trade-b", b)
    _, read_a = store.read("trade-a")
    _, read_b = store.read("trade-b")
    assert read_a.approved_risk_amount == Decimal("120")
    assert read_b.approved_risk_amount == Decimal("50")


def test_list_trade_ids(store: MT5RecommendationProvenancePersistence) -> None:
    store.write("trade-a", _provenance())
    store.write("trade-b", _provenance())
    assert store.list_trade_ids() == ("trade-a", "trade-b")


# --- coexistence / failure independence with Stage 10E's own tracking store ---


def test_provenance_and_tracking_files_coexist_in_same_directory(tmp_path: Path) -> None:
    tracking_store = MT5RecommendationPersistence(tmp_path)
    provenance_store = MT5RecommendationProvenancePersistence(tmp_path)

    tracking_store.write("trade-1", default_tracked_recommendation())
    provenance_store.write("trade-1", _provenance())

    tracking_status, tracked = tracking_store.read("trade-1")
    provenance_status, provenance = provenance_store.read("trade-1")
    assert tracking_status == "VALID"
    assert provenance_status == "VALID"
    assert tracked is not None
    assert provenance is not None


def test_corrupting_provenance_file_does_not_affect_tracking_file(tmp_path: Path) -> None:
    tracking_store = MT5RecommendationPersistence(tmp_path)
    provenance_store = MT5RecommendationProvenancePersistence(tmp_path)

    tracking_store.write("trade-1", default_tracked_recommendation())
    provenance_store.write("trade-1", _provenance())

    (tmp_path / "trade-1.provenance.json").write_text("{corrupt", encoding="utf-8")

    tracking_status, tracked = tracking_store.read("trade-1")
    provenance_status, _ = provenance_store.read("trade-1")
    assert tracking_status == "VALID"
    assert tracked is not None
    assert provenance_status == "CORRUPT"


def test_corrupting_tracking_file_does_not_affect_provenance_file(tmp_path: Path) -> None:
    tracking_store = MT5RecommendationPersistence(tmp_path)
    provenance_store = MT5RecommendationProvenancePersistence(tmp_path)

    tracking_store.write("trade-1", default_tracked_recommendation())
    provenance_store.write("trade-1", _provenance())

    (tmp_path / "trade-1.json").write_text("{corrupt", encoding="utf-8")

    tracking_status, _ = tracking_store.read("trade-1")
    provenance_status, provenance = provenance_store.read("trade-1")
    assert tracking_status == "CORRUPT"
    assert provenance_status == "VALID"
    assert provenance is not None


def test_provenance_absent_for_trade_id_created_before_this_feature(tmp_path: Path) -> None:
    """A tracking file with no sibling provenance file (e.g. persisted
    before this feature existed) must report ABSENT, never a fabricated
    provenance record."""
    tracking_store = MT5RecommendationPersistence(tmp_path)
    provenance_store = MT5RecommendationProvenancePersistence(tmp_path)

    tracking_store.write("trade-1", default_tracked_recommendation())

    tracking_status, _ = tracking_store.read("trade-1")
    provenance_status, provenance = provenance_store.read("trade-1")
    assert tracking_status == "VALID"
    assert provenance_status == "ABSENT"
    assert provenance is None


# --- restart scenario ---


def test_restart_load_scenario(tmp_path: Path) -> None:
    tracking_store = MT5RecommendationPersistence(tmp_path)
    provenance_store = MT5RecommendationProvenancePersistence(tmp_path)

    tracking_store.write("T1", default_tracked_recommendation())
    provenance_store.write(
        "T1",
        _provenance(family=StrategyFamily.BREAKOUT, approved_risk_amount=Decimal("77"), account_currency="DKK"),
    )

    # simulate restart: fresh store instances over the same directory
    reloaded_tracking_store = MT5RecommendationPersistence(tmp_path)
    reloaded_provenance_store = MT5RecommendationProvenancePersistence(tmp_path)

    _, tracked = reloaded_tracking_store.read("T1")
    _, provenance = reloaded_provenance_store.read("T1")

    assert tracked is not None
    assert provenance is not None
    assert provenance.family is StrategyFamily.BREAKOUT
    assert provenance.approved_risk_amount == Decimal("77")
    assert provenance.account_currency == "DKK"


# --- deterministic serialization ---


def test_deterministic_serialization() -> None:
    provenance = _provenance()
    assert provenance.model_dump_json() == provenance.model_dump_json()


# --- module hygiene ---


def test_no_mt5_import() -> None:
    import inspect

    import app.mt5.recommendation_provenance_persistence as module

    source = inspect.getsource(module)
    assert "MetaTrader5" not in source
    assert "app.mt5.client" not in source
