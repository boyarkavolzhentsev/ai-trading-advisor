"""Tests for app.flow_analysts.liquidation.LiquidationAnalyst."""

from __future__ import annotations

from app.core.enums.flow_analysis import AnalysisDimension, AnalystOutcome, LiquidationActivity, LiquidationPressure
from app.core.enums.instrument import ContractType
from app.core.enums.order import OrderSide
from app.core.enums.quality import FeatureQuality
from app.flow_analysts.liquidation import LiquidationAnalyst
from tests.flow_analysts_support import WINDOW_10S, build_snapshot, liquidation, make_engine


def _pressure(result, window="10s"):
    return [o for o in result.observations if o.dimension is AnalysisDimension.DIRECTIONAL_PRESSURE and o.window == window]


def _activity(result, window="10s"):
    return [o for o in result.observations if o.dimension is AnalysisDimension.ACTIVITY_PRESENCE and o.window == window]


def test_long_liquidations_dominant() -> None:
    # A forced SELL closes a long -> counted as long-liquidation volume.
    engine = make_engine(windows=(WINDOW_10S,))
    engine.record_liquidation(liquidation(seconds_ago=1, side=OrderSide.SELL, quantity="5"))
    engine.record_liquidation(liquidation(seconds_ago=1, side=OrderSide.BUY, quantity="1"))
    snapshot = build_snapshot(engine)

    result = LiquidationAnalyst().analyze(snapshot)

    assert result.status is AnalystOutcome.ANALYZED
    assert _pressure(result)[0].value == LiquidationPressure.LONG_LIQUIDATIONS_DOMINANT.value


def test_short_liquidations_dominant() -> None:
    engine = make_engine(windows=(WINDOW_10S,))
    engine.record_liquidation(liquidation(seconds_ago=1, side=OrderSide.BUY, quantity="5"))
    engine.record_liquidation(liquidation(seconds_ago=1, side=OrderSide.SELL, quantity="1"))
    snapshot = build_snapshot(engine)

    result = LiquidationAnalyst().analyze(snapshot)

    assert _pressure(result)[0].value == LiquidationPressure.SHORT_LIQUIDATIONS_DOMINANT.value


def test_balanced_with_activity_present() -> None:
    engine = make_engine(windows=(WINDOW_10S,))
    engine.record_liquidation(liquidation(seconds_ago=1, side=OrderSide.BUY, quantity="3"))
    engine.record_liquidation(liquidation(seconds_ago=1, side=OrderSide.SELL, quantity="3"))
    snapshot = build_snapshot(engine)

    result = LiquidationAnalyst().analyze(snapshot)

    assert _pressure(result)[0].value == LiquidationPressure.BALANCED.value
    assert _activity(result)[0].value == LiquidationActivity.ACTIVITY_PRESENT.value


def test_no_activity_is_valid_zero_not_unavailable() -> None:
    engine = make_engine(windows=(WINDOW_10S,))
    snapshot = build_snapshot(engine)
    assert snapshot.liquidation["10s"].status.quality is FeatureQuality.VALID

    result = LiquidationAnalyst().analyze(snapshot)

    assert result.status is AnalystOutcome.ANALYZED
    assert _activity(result)[0].value == LiquidationActivity.NO_ACTIVITY.value
    assert _activity(result)[0].quality is FeatureQuality.VALID
    assert _pressure(result)[0].value == LiquidationPressure.BALANCED.value
    assert _pressure(result)[0].quality is FeatureQuality.VALID


def test_full_abstention_when_no_windows_configured() -> None:
    engine = make_engine(windows=())
    snapshot = build_snapshot(engine)
    assert snapshot.liquidation == {}

    result = LiquidationAnalyst().analyze(snapshot)

    assert result.status is AnalystOutcome.ABSTAINED
    assert result.quality is FeatureQuality.UNAVAILABLE
    assert len(result.abstention_reasons) >= 1


def test_partial_quality_propagates_from_truncated_history() -> None:
    from app.market_data.realtime.buffers import BoundedBuffer

    engine = make_engine(windows=(WINDOW_10S,))
    history = engine.history_for("BTCUSDT", ContractType.PERPETUAL)
    history.liquidations = BoundedBuffer(maxlen=1)
    engine.record_liquidation(liquidation(seconds_ago=9, side=OrderSide.SELL, quantity="1"))
    engine.record_liquidation(liquidation(seconds_ago=1, side=OrderSide.SELL, quantity="1"))
    snapshot = build_snapshot(engine)
    assert snapshot.liquidation["10s"].status.quality is FeatureQuality.PARTIAL

    result = LiquidationAnalyst().analyze(snapshot)

    assert _pressure(result)[0].quality is FeatureQuality.PARTIAL
    assert result.quality is FeatureQuality.PARTIAL


def test_evidence_and_provenance() -> None:
    engine = make_engine(windows=(WINDOW_10S,))
    engine.record_liquidation(liquidation(seconds_ago=1, side=OrderSide.SELL, quantity="1"))
    snapshot = build_snapshot(engine)

    result = LiquidationAnalyst().analyze(snapshot)

    feature_names = {e.feature_name for e in result.evidence}
    assert "liquidation.liquidation_imbalance" in feature_names
    assert "liquidation.liquidation_count" in feature_names
    assert result.provenance["liquidation"] == snapshot.provenance["liquidation"]
    for observation in result.observations:
        for ref in observation.evidence_refs:
            assert 0 <= ref < len(result.evidence)


def test_no_burst_cluster_or_unusual_vocabulary() -> None:
    forbidden = {"BURST", "CLUSTER", "UNUSUAL", "EXTREME"}
    assert forbidden.isdisjoint(member.value for member in LiquidationPressure)
    assert forbidden.isdisjoint(member.value for member in LiquidationActivity)


def test_multi_symbol_no_leakage() -> None:
    analyst = LiquidationAnalyst()
    engine = make_engine(windows=(WINDOW_10S,))
    engine.record_liquidation(liquidation("BTCUSDT", seconds_ago=1, side=OrderSide.SELL, quantity="5"))
    engine.record_liquidation(liquidation("ETHUSDT", seconds_ago=1, side=OrderSide.BUY, quantity="5"))

    btc = analyst.analyze(build_snapshot(engine, symbol="BTCUSDT"))
    eth = analyst.analyze(build_snapshot(engine, symbol="ETHUSDT"))

    assert _pressure(btc)[0].value == LiquidationPressure.LONG_LIQUIDATIONS_DOMINANT.value
    assert _pressure(eth)[0].value == LiquidationPressure.SHORT_LIQUIDATIONS_DOMINANT.value


def test_repeated_calls_deterministic() -> None:
    analyst = LiquidationAnalyst()
    engine = make_engine(windows=(WINDOW_10S,))
    engine.record_liquidation(liquidation(seconds_ago=1, side=OrderSide.SELL, quantity="1"))
    snapshot = build_snapshot(engine)

    assert analyst.analyze(snapshot) == analyst.analyze(snapshot)
