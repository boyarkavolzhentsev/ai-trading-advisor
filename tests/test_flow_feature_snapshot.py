"""Contract-level tests for FlowFeatureSnapshot and its shared primitives."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.enums.instrument import ContractType
from app.core.enums.quality import FeatureQuality
from app.core.models.analytics_window import AnalyticsWindow
from app.core.models.feature_status import FeatureStatus
from app.core.models.flow_feature_snapshot import FlowFeatureSnapshot

NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
WINDOW = AnalyticsWindow(label="1m", duration=timedelta(minutes=1))


def test_feature_status_defaults() -> None:
    status = FeatureStatus(quality=FeatureQuality.VALID)
    assert status.sample_count == 0
    assert status.reasons == []


def test_feature_status_rejects_negative_sample_count() -> None:
    with pytest.raises(ValidationError):
        FeatureStatus(quality=FeatureQuality.VALID, sample_count=-1)


def test_flow_feature_snapshot_is_frozen() -> None:
    snapshot = FlowFeatureSnapshot(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        observation_time=NOW,
        windows=(WINDOW,),
    )
    with pytest.raises(ValidationError):
        snapshot.symbol = "ETHUSDT"  # type: ignore[misc]


def test_flow_feature_snapshot_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        FlowFeatureSnapshot(
            symbol="BTCUSDT",
            contract_type=ContractType.PERPETUAL,
            observation_time=NOW,
            windows=(WINDOW,),
            unexpected_field=True,
        )


def test_flow_feature_snapshot_rejects_naive_timestamp() -> None:
    with pytest.raises(ValidationError):
        FlowFeatureSnapshot(
            symbol="BTCUSDT",
            contract_type=ContractType.PERPETUAL,
            observation_time=datetime(2026, 1, 1, 12, 0, 0),  # naive
            windows=(WINDOW,),
        )


def test_flow_feature_snapshot_defaults_are_empty_not_none() -> None:
    snapshot = FlowFeatureSnapshot(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        observation_time=NOW,
        windows=(WINDOW,),
    )
    assert snapshot.taker_flow == {}
    assert snapshot.liquidation == {}
    assert snapshot.order_book is None
    assert snapshot.open_interest is None
    assert snapshot.funding is None
    assert snapshot.price_context == {}
    assert snapshot.cross_features == {}
    assert snapshot.provenance == {}
