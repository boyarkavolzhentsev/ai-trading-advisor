"""Real local-filesystem regression test (Windows-observable): the previous
(rejected) ``f"{logical_cycle_id}:{family.value}"`` identity format could
silently produce an NTFS Alternate-Data-Stream path instead of a normal
file, making the resulting ``trade_id`` invisible to
``MT5RecommendationPersistence.list_trade_ids()``/
``MT5RecommendationProvenancePersistence.list_trade_ids()`` (both use
``Path.glob``, which never enumerates ADS streams). This test proves the
adopted ``f"{logical_cycle_id}__{family.value}"`` format round-trips
correctly through the real, unmodified persistence classes - no MT5
connection involved, no Stage0D persistence code modified.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.application.identity import derive_trade_id, derive_trade_ids
from app.core.enums.market import MarketType
from app.core.enums.strategy_router import StrategyFamily
from app.core.enums.trade import TradeDirection
from app.core.models.final_recommendation_provenance import FinalRecommendationProvenance
from app.core.models.mt5_tracking import MT5TrackedRecommendation
from app.core.models.position import PositionRecord
from app.mt5.recommendation_persistence import MT5RecommendationPersistence
from app.mt5.recommendation_provenance_persistence import MT5RecommendationProvenancePersistence

_SIGNAL_TIME = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
_VALID_UNTIL = datetime(2026, 5, 1, 16, 0, 0, tzinfo=UTC)


@pytest.mark.parametrize("family", list(StrategyFamily))
def test_derived_trade_id_charset_is_windows_safe(family: StrategyFamily) -> None:
    trade_id = derive_trade_id("cycle-2026-05-01", family)
    assert ":" not in trade_id
    assert "/" not in trade_id
    assert "\\" not in trade_id


def _real_tracked_recommendation(trade_id: str) -> MT5TrackedRecommendation:
    """A fully valid, real ``MT5TrackedRecommendation`` - this test exercises
    ``MT5RecommendationPersistence``'s own real ``write``/``read``/
    ``list_trade_ids`` round-trip, so the payload must pass real
    validation, not merely construct."""
    position_record = PositionRecord(
        trade_id=trade_id,
        symbol="EURUSD",
        market=MarketType.FX,
        direction=TradeDirection.LONG,
        signal_time=_SIGNAL_TIME,
        valid_until=_VALID_UNTIL,
        planned_entry=Decimal("1.1000"),
        stop_loss=Decimal("1.0900"),
    )
    return MT5TrackedRecommendation(position_record=position_record, approved_broker_volume=Decimal("0.50"))


def test_tracking_persistence_round_trip_with_derived_trade_id(tmp_path: Path) -> None:
    trade_id = derive_trade_id("cycle-2026-05-01", StrategyFamily.TREND_FOLLOWING)
    persistence = MT5RecommendationPersistence(tmp_path)
    tracked = _real_tracked_recommendation(trade_id)

    assert persistence.write(trade_id, tracked) is True
    read_status, read_back = persistence.read(trade_id)
    assert read_status == "VALID"
    assert read_back is not None
    assert read_back.position_record.trade_id == trade_id
    assert trade_id in persistence.list_trade_ids()


def test_provenance_persistence_round_trip_with_derived_trade_id(tmp_path: Path) -> None:
    trade_id = derive_trade_id("cycle-2026-05-01", StrategyFamily.MEAN_REVERSION)
    persistence = MT5RecommendationProvenancePersistence(tmp_path)
    provenance = FinalRecommendationProvenance(
        trade_id=trade_id, family=StrategyFamily.MEAN_REVERSION, approved_risk_amount=Decimal("25.00"), account_currency="USD"
    )

    assert persistence.write(trade_id, provenance) is True
    read_status, read_back = persistence.read(trade_id)
    assert read_status == "VALID"
    assert read_back is not None
    assert read_back.trade_id == trade_id
    assert trade_id in persistence.list_trade_ids()


def test_every_family_derived_trade_id_round_trips(tmp_path: Path) -> None:
    persistence = MT5RecommendationPersistence(tmp_path)
    trade_ids = derive_trade_ids("cycle-2026-05-01")
    for trade_id in trade_ids.values():
        tracked = _real_tracked_recommendation(trade_id)
        assert persistence.write(trade_id, tracked) is True

    listed = set(persistence.list_trade_ids())
    assert listed == set(trade_ids.values())
