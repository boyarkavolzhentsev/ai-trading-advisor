"""Stage 10E ``MT5RecommendationPersistence``: typed read status, atomic
write, corruption/unavailable fail-closed, stable trade_id path behavior,
full restart round-trips via the persisted store."""

from __future__ import annotations

import os
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.core.enums.mt5_history import MT5DealEntry
from app.core.enums.mt5_matching import MT5MatchOutcome
from app.core.enums.trade import TradeStatus
from app.mt5.recommendation_persistence import MT5RecommendationPersistence
from app.mt5.tracker import advance_tracked_recommendation
from tests.mt5_matching_support import SIGNAL_TIME, default_candidate_deal, default_tracked_recommendation


@pytest.fixture
def store(tmp_path: Path) -> MT5RecommendationPersistence:
    return MT5RecommendationPersistence(tmp_path)


# --- typed read status ---


def test_absent_when_never_written(store: MT5RecommendationPersistence) -> None:
    status, value = store.read("trade-1")
    assert status == "ABSENT"
    assert value is None


def test_valid_round_trip(store: MT5RecommendationPersistence) -> None:
    tracked = default_tracked_recommendation()
    assert store.write("trade-1", tracked) is True
    status, value = store.read("trade-1")
    assert status == "VALID"
    assert value == tracked


def test_corrupt_json(store: MT5RecommendationPersistence, tmp_path: Path) -> None:
    (tmp_path / "trade-1.json").write_text("{not valid json", encoding="utf-8")
    status, value = store.read("trade-1")
    assert status == "CORRUPT"
    assert value is None


def test_corrupt_schema_mismatch(store: MT5RecommendationPersistence, tmp_path: Path) -> None:
    (tmp_path / "trade-1.json").write_text('{"foo": "bar"}', encoding="utf-8")
    status, value = store.read("trade-1")
    assert status == "CORRUPT"
    assert value is None


def test_unavailable_directory_missing(tmp_path: Path) -> None:
    store = MT5RecommendationPersistence(tmp_path / "does-not-exist")
    status, value = store.read("trade-1")
    assert status == "ABSENT"
    assert value is None


# --- atomic write ---


def test_write_creates_no_stray_tmp_file_on_success(store: MT5RecommendationPersistence, tmp_path: Path) -> None:
    store.write("trade-1", default_tracked_recommendation())
    assert not (tmp_path / "trade-1.json.tmp").exists()
    assert (tmp_path / "trade-1.json").exists()


def test_failed_replace_preserves_existing_valid_file(store: MT5RecommendationPersistence, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    original = default_tracked_recommendation()
    store.write("trade-1", original)

    def _boom(*args: object, **kwargs: object) -> None:
        raise OSError("simulated disk failure")

    monkeypatch.setattr(os, "replace", _boom)
    updated = default_tracked_recommendation(approved_broker_volume=Decimal("9"))
    ok = store.write("trade-1", updated)
    assert ok is False

    monkeypatch.undo()
    status, value = store.read("trade-1")
    assert status == "VALID"
    assert value == original
    assert not (tmp_path / "trade-1.json.tmp").exists()


# --- stable trade_id path behavior ---


def test_unsafe_trade_id_with_path_separator_rejected_on_write(store: MT5RecommendationPersistence) -> None:
    assert store.write("../escape", default_tracked_recommendation()) is False


def test_unsafe_trade_id_with_path_separator_rejected_on_read(store: MT5RecommendationPersistence) -> None:
    status, value = store.read("nested/path")
    assert status == "UNAVAILABLE"
    assert value is None


def test_empty_trade_id_rejected(store: MT5RecommendationPersistence) -> None:
    assert store.write("", default_tracked_recommendation()) is False


def test_distinct_trade_ids_do_not_collide(store: MT5RecommendationPersistence) -> None:
    a = default_tracked_recommendation()
    b = default_tracked_recommendation(approved_broker_volume=Decimal("2"))
    store.write("trade-a", a)
    store.write("trade-b", b)
    _, read_a = store.read("trade-a")
    _, read_b = store.read("trade-b")
    assert read_a.approved_broker_volume == Decimal("1")
    assert read_b.approved_broker_volume == Decimal("2")


def test_list_trade_ids(store: MT5RecommendationPersistence) -> None:
    store.write("trade-a", default_tracked_recommendation())
    store.write("trade-b", default_tracked_recommendation())
    assert store.list_trade_ids() == ("trade-a", "trade-b")


# --- restart scenarios, end-to-end through the store ---


def test_restart_before_fill_via_store(store: MT5RecommendationPersistence) -> None:
    tracked = default_tracked_recommendation()
    store.write("trade-1", tracked)

    _, reloaded = store.read("trade-1")
    updated = advance_tracked_recommendation(
        as_of=SIGNAL_TIME + timedelta(minutes=1),
        tracked=reloaded,
        deals=(default_candidate_deal(),),
        history_read_status="OK",
        history_covers_until=SIGNAL_TIME + timedelta(minutes=1),
        already_claimed_position_ids=(),
    )
    store.write("trade-1", updated)

    _, final = store.read("trade-1")
    assert final.matched_position_id == 7001
    assert final.position_record.status is TradeStatus.OPEN


def test_restart_after_terminal_persistence_via_store(store: MT5RecommendationPersistence) -> None:
    tracked = default_tracked_recommendation()
    entry = default_candidate_deal(ticket=1)
    exit_deal = default_candidate_deal(ticket=2, entry=MT5DealEntry.OUT, time=SIGNAL_TIME + timedelta(minutes=3), profit=Decimal("50"))
    terminal = advance_tracked_recommendation(
        as_of=SIGNAL_TIME + timedelta(minutes=4),
        tracked=tracked,
        deals=(entry, exit_deal),
        history_read_status="OK",
        history_covers_until=SIGNAL_TIME + timedelta(minutes=4),
        already_claimed_position_ids=(),
    )
    store.write("trade-1", terminal)

    _, reloaded = store.read("trade-1")
    assert reloaded.position_record.status is TradeStatus.WIN

    again = advance_tracked_recommendation(
        as_of=SIGNAL_TIME + timedelta(minutes=100),
        tracked=reloaded,
        deals=(entry, exit_deal),
        history_read_status="OK",
        history_covers_until=SIGNAL_TIME + timedelta(minutes=100),
        already_claimed_position_ids=(),
    )
    assert again.position_record.status is TradeStatus.WIN
    assert again.last_match_outcome is MT5MatchOutcome.MATCHED
