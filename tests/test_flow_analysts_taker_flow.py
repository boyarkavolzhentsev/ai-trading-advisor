"""Tests for app.flow_analysts.taker_flow.TakerFlowAnalyst."""

from __future__ import annotations

from decimal import Decimal

from app.core.enums.flow_analysis import AgreementVerdict, AnalysisDimension, AnalystOutcome, OrdinalTrend, TakerFlowPressure
from app.core.enums.instrument import ContractType
from app.core.enums.order import OrderSide
from app.core.enums.quality import FeatureQuality
from app.flow_analysts.taker_flow import TakerFlowAnalyst
from tests.flow_analysts_support import NOW, WINDOW_10S, build_snapshot, make_engine, trade


def _pressure(result, window: str | None = None):
    matches = [o for o in result.observations if o.dimension is AnalysisDimension.DIRECTIONAL_PRESSURE and o.window == window]
    return matches


def test_buy_dominant() -> None:
    engine = make_engine(windows=(WINDOW_10S,))
    engine.record_trade(trade(seconds_ago=1, side=OrderSide.BUY, price="100", quantity="3", trade_id=1))
    engine.record_trade(trade(seconds_ago=1, side=OrderSide.SELL, price="100", quantity="1", trade_id=2))
    snapshot = build_snapshot(engine)

    result = TakerFlowAnalyst().analyze(snapshot)

    assert result.status is AnalystOutcome.ANALYZED
    pressure = _pressure(result, "10s")
    assert len(pressure) == 1
    assert pressure[0].value == TakerFlowPressure.BUY_DOMINANT.value
    assert pressure[0].quality is FeatureQuality.VALID


def test_sell_dominant() -> None:
    engine = make_engine(windows=(WINDOW_10S,))
    engine.record_trade(trade(seconds_ago=1, side=OrderSide.SELL, price="100", quantity="3", trade_id=1))
    engine.record_trade(trade(seconds_ago=1, side=OrderSide.BUY, price="100", quantity="1", trade_id=2))
    snapshot = build_snapshot(engine)

    result = TakerFlowAnalyst().analyze(snapshot)

    pressure = _pressure(result, "10s")
    assert pressure[0].value == TakerFlowPressure.SELL_DOMINANT.value


def test_balanced_is_valid_zero_not_missing() -> None:
    engine = make_engine(windows=(WINDOW_10S,))
    engine.record_trade(trade(seconds_ago=1, side=OrderSide.BUY, price="100", quantity="2", trade_id=1))
    engine.record_trade(trade(seconds_ago=1, side=OrderSide.SELL, price="100", quantity="2", trade_id=2))
    snapshot = build_snapshot(engine)

    result = TakerFlowAnalyst().analyze(snapshot)

    pressure = _pressure(result, "10s")
    assert pressure[0].value == TakerFlowPressure.BALANCED.value
    assert pressure[0].quality is FeatureQuality.VALID


def test_full_abstention_when_no_trades_at_all() -> None:
    engine = make_engine(windows=())
    snapshot = build_snapshot(engine)

    result = TakerFlowAnalyst().analyze(snapshot)

    assert result.status is AnalystOutcome.ABSTAINED
    assert result.observations == ()
    assert result.evidence == ()
    assert result.quality is FeatureQuality.UNAVAILABLE
    assert len(result.abstention_reasons) >= 1


def test_partial_quality_propagates_from_truncated_history() -> None:
    from app.market_data.realtime.buffers import BoundedBuffer

    engine = make_engine(windows=(WINDOW_10S,))
    history = engine.history_for("BTCUSDT", ContractType.PERPETUAL)
    history.trades = BoundedBuffer(maxlen=1)
    engine.record_trade(trade(seconds_ago=9, side=OrderSide.BUY, price="100", quantity="1", trade_id=1))
    engine.record_trade(trade(seconds_ago=1, side=OrderSide.BUY, price="100", quantity="1", trade_id=2))
    snapshot = build_snapshot(engine)
    assert snapshot.taker_flow["10s"].status.quality is FeatureQuality.PARTIAL

    result = TakerFlowAnalyst().analyze(snapshot)

    pressure = _pressure(result, "10s")
    assert pressure[0].quality is FeatureQuality.PARTIAL
    assert result.quality is FeatureQuality.PARTIAL


def test_persistence_all_agree_across_windows() -> None:
    engine = make_engine()
    engine.record_trade(trade(seconds_ago=1, side=OrderSide.BUY, price="100", quantity="1", trade_id=1))
    snapshot = build_snapshot(engine)

    result = TakerFlowAnalyst().analyze(snapshot)

    persistence = [o for o in result.observations if o.dimension is AnalysisDimension.PERSISTENCE]
    assert len(persistence) == 1
    assert persistence[0].value == AgreementVerdict.ALL_AGREE.value


def test_persistence_mixed_across_windows() -> None:
    engine = make_engine()
    # In the last 10s: net BUY. Between 10s and 60s ago: a much larger net SELL.
    engine.record_trade(trade(seconds_ago=1, side=OrderSide.BUY, price="100", quantity="1", trade_id=1))
    engine.record_trade(trade(seconds_ago=45, side=OrderSide.SELL, price="100", quantity="10", trade_id=2))
    snapshot = build_snapshot(engine)

    result = TakerFlowAnalyst().analyze(snapshot)

    assert snapshot.taker_flow["10s"].delta == Decimal("1")
    assert snapshot.taker_flow["1m"].delta == Decimal("-9")
    persistence = [o for o in result.observations if o.dimension is AnalysisDimension.PERSISTENCE]
    assert persistence[0].value == AgreementVerdict.MIXED.value


def test_magnitude_trend_increasing_when_shortest_rate_exceeds_longest() -> None:
    engine = make_engine()
    engine.record_trade(trade(seconds_ago=1, side=OrderSide.BUY, price="100", quantity="1", trade_id=1))
    engine.record_trade(trade(seconds_ago=45, side=OrderSide.SELL, price="100", quantity="10", trade_id=2))
    snapshot = build_snapshot(engine)

    result = TakerFlowAnalyst().analyze(snapshot)

    trend = [o for o in result.observations if o.dimension is AnalysisDimension.MAGNITUDE_TREND]
    assert len(trend) == 1
    # delta_rate(10s) = 1/10 = 0.1 ; delta_rate(1m) = -9/60 = -0.15 -> shortest > longest
    assert trend[0].value == OrdinalTrend.INCREASING.value
    assert len(trend[0].evidence_refs) == 2


def test_magnitude_trend_stable_when_rates_equal() -> None:
    engine = make_engine()
    # Only trades within the last 10s -> delta(10s) == delta(1m) == same total,
    # but rates differ by duration UNLESS scaled: pick 1 in 10s window and an
    # extra +5 between 10s-60s ago so delta(1m)=6 and both rates equal 0.1.
    engine.record_trade(trade(seconds_ago=1, side=OrderSide.BUY, price="100", quantity="1", trade_id=1))
    engine.record_trade(trade(seconds_ago=45, side=OrderSide.BUY, price="100", quantity="5", trade_id=2))
    snapshot = build_snapshot(engine)

    assert snapshot.taker_flow["10s"].delta_rate == Decimal("1") / Decimal("10")
    assert snapshot.taker_flow["1m"].delta_rate == Decimal("6") / Decimal("60")

    result = TakerFlowAnalyst().analyze(snapshot)
    trend = [o for o in result.observations if o.dimension is AnalysisDimension.MAGNITUDE_TREND]
    assert trend[0].value == OrdinalTrend.STABLE.value

    persistence = [o for o in result.observations if o.dimension is AnalysisDimension.PERSISTENCE]
    assert persistence[0].value == AgreementVerdict.ALL_AGREE.value


def test_persistence_and_magnitude_trend_insufficient_with_single_window() -> None:
    engine = make_engine(windows=(WINDOW_10S,))
    engine.record_trade(trade(seconds_ago=1, side=OrderSide.BUY, price="100", quantity="1", trade_id=1))
    snapshot = build_snapshot(engine)

    result = TakerFlowAnalyst().analyze(snapshot)

    persistence = [o for o in result.observations if o.dimension is AnalysisDimension.PERSISTENCE]
    trend = [o for o in result.observations if o.dimension is AnalysisDimension.MAGNITUDE_TREND]
    assert persistence[0].value == AgreementVerdict.INSUFFICIENT_DATA.value
    assert trend[0].value == OrdinalTrend.INSUFFICIENT_DATA.value


def test_every_observation_evidence_refs_resolve() -> None:
    engine = make_engine()
    engine.record_trade(trade(seconds_ago=1, side=OrderSide.BUY, price="100", quantity="1", trade_id=1))
    snapshot = build_snapshot(engine)

    result = TakerFlowAnalyst().analyze(snapshot)

    for observation in result.observations:
        assert len(observation.evidence_refs) >= 1
        for ref in observation.evidence_refs:
            assert 0 <= ref < len(result.evidence)


def test_evidence_feature_names_and_provenance() -> None:
    engine = make_engine(windows=(WINDOW_10S,))
    engine.record_trade(trade(seconds_ago=1, side=OrderSide.BUY, price="100", quantity="1", trade_id=1))
    snapshot = build_snapshot(engine)

    result = TakerFlowAnalyst().analyze(snapshot)

    feature_names = {e.feature_name for e in result.evidence}
    assert "taker_flow.delta" in feature_names
    assert "taker_flow.delta_rate" in feature_names
    assert result.provenance["taker_flow"] == snapshot.provenance["taker_flow"]
    assert all(e.provenance == snapshot.provenance["taker_flow"] for e in result.evidence)


def test_result_quality_is_worse_of_observation_qualities() -> None:
    engine = make_engine(windows=(WINDOW_10S,))
    engine.record_trade(trade(seconds_ago=1, side=OrderSide.BUY, price="100", quantity="1", trade_id=1))
    snapshot = build_snapshot(engine)

    result = TakerFlowAnalyst().analyze(snapshot)

    assert result.quality is FeatureQuality.VALID
    assert all(o.quality is FeatureQuality.VALID for o in result.observations)


def test_multi_symbol_no_leakage_same_analyst_instance() -> None:
    analyst = TakerFlowAnalyst()
    engine = make_engine(windows=(WINDOW_10S,))
    engine.record_trade(trade("BTCUSDT", seconds_ago=1, side=OrderSide.BUY, price="100", quantity="1", trade_id=1))
    engine.record_trade(trade("ETHUSDT", seconds_ago=1, side=OrderSide.SELL, price="3000", quantity="5", trade_id=1))

    btc_snapshot = build_snapshot(engine, symbol="BTCUSDT")
    eth_snapshot = build_snapshot(engine, symbol="ETHUSDT")

    btc_result = analyst.analyze(btc_snapshot)
    eth_result = analyst.analyze(eth_snapshot)

    assert btc_result.symbol == "BTCUSDT"
    assert _pressure(btc_result, "10s")[0].value == TakerFlowPressure.BUY_DOMINANT.value
    assert eth_result.symbol == "ETHUSDT"
    assert _pressure(eth_result, "10s")[0].value == TakerFlowPressure.SELL_DOMINANT.value


def test_multiple_contract_types_no_leakage() -> None:
    analyst = TakerFlowAnalyst()
    engine = make_engine(windows=(WINDOW_10S,))
    engine.record_trade(
        trade("BTCUSDT", seconds_ago=1, side=OrderSide.BUY, price="100", quantity="1", trade_id=1, contract_type=ContractType.PERPETUAL)
    )
    engine.record_trade(
        trade("BTCUSDT", seconds_ago=1, side=OrderSide.SELL, price="100", quantity="9", trade_id=1, contract_type=ContractType.SPOT)
    )

    perp = build_snapshot(engine, symbol="BTCUSDT", contract_type=ContractType.PERPETUAL)
    spot = build_snapshot(engine, symbol="BTCUSDT", contract_type=ContractType.SPOT)

    perp_result = analyst.analyze(perp)
    spot_result = analyst.analyze(spot)

    assert _pressure(perp_result, "10s")[0].value == TakerFlowPressure.BUY_DOMINANT.value
    assert _pressure(spot_result, "10s")[0].value == TakerFlowPressure.SELL_DOMINANT.value


def test_repeated_calls_are_deterministic_no_state_leakage() -> None:
    analyst = TakerFlowAnalyst()
    engine = make_engine(windows=(WINDOW_10S,))
    engine.record_trade(trade(seconds_ago=1, side=OrderSide.BUY, price="100", quantity="1", trade_id=1))
    snapshot = build_snapshot(engine)

    first = analyst.analyze(snapshot)
    second = analyst.analyze(snapshot)

    assert first == second


def test_snapshot_not_mutated_by_analysis() -> None:
    engine = make_engine(windows=(WINDOW_10S,))
    engine.record_trade(trade(seconds_ago=1, side=OrderSide.BUY, price="100", quantity="1", trade_id=1))
    snapshot = build_snapshot(engine)
    before = snapshot.model_copy(deep=True)

    TakerFlowAnalyst().analyze(snapshot)

    assert snapshot == before
