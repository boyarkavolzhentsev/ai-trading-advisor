"""Tests for app.flow_analysts.price_flow_relationship.PriceFlowRelationshipAnalyst."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.core.enums.flow_analysis import AnalysisDimension, AnalystOutcome, CorrelationRelationship, PriceFlowRelationship
from app.core.enums.instrument import ContractType
from app.core.enums.order import OrderSide
from app.core.enums.quality import FeatureQuality
from app.core.models.analytics_window import AnalyticsWindow
from app.core.models.cross_feature_observation import CrossFeatureObservation
from app.core.models.feature_status import FeatureStatus
from app.core.models.flow_feature_snapshot import FlowFeatureSnapshot
from app.core.models.trade_event import TradeEvent
from app.flow_analysts.price_flow_relationship import PriceFlowRelationshipAnalyst
from tests.flow_analysts_support import WINDOW_10S, build_snapshot, liquidation, make_engine, open_interest, trade

NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
WINDOW_1M = AnalyticsWindow(label="1m", duration=timedelta(minutes=1))


def _dim(result, dimension, window="10s"):
    return [o for o in result.observations if o.dimension is dimension and o.window == window]


def test_correlation_positive_relationship() -> None:
    # Mirrors test_flow_engine.py's cross-feature-correlation construction:
    # each iteration's two trades sit inside their own, fully separate,
    # already-closed 10s window so return_pct and taker delta co-move exactly.
    base = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
    engine = make_engine(windows=(WINDOW_10S,))
    snapshot = None
    for i in range(4):
        bucket_start = base + timedelta(seconds=10 * i)
        observation_time = bucket_start + timedelta(seconds=10)
        engine.record_trade(
            TradeEvent(
                symbol="BTCUSDT",
                contract_type=ContractType.PERPETUAL,
                trade_id=i * 2,
                price=Decimal("100"),
                quantity=Decimal(str(1 + i)),
                side=OrderSide.BUY,
                timestamp=bucket_start + timedelta(seconds=3),
                source="test:trade",
            )
        )
        engine.record_trade(
            TradeEvent(
                symbol="BTCUSDT",
                contract_type=ContractType.PERPETUAL,
                trade_id=i * 2 + 1,
                price=Decimal(str(100 + (1 + i) * 2)),
                quantity=Decimal(str(1 + i)),
                side=OrderSide.BUY,
                timestamp=bucket_start + timedelta(seconds=8),
                source="test:trade",
            )
        )
        snapshot = engine.build_snapshot(
            symbol="BTCUSDT", contract_type=ContractType.PERPETUAL, observation_time=observation_time, default_source="test"
        )
    assert snapshot is not None
    assert snapshot.cross_features["10s"].correlation == 1.0

    result = PriceFlowRelationshipAnalyst().analyze(snapshot)

    correlation_obs = [o for o in result.observations if o.dimension is AnalysisDimension.CORRELATION_RELATIONSHIP]
    assert correlation_obs[0].value == CorrelationRelationship.POSITIVE_RELATIONSHIP.value


def _minimal_snapshot(cross_features: dict) -> FlowFeatureSnapshot:
    return FlowFeatureSnapshot(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        observation_time=NOW,
        windows=(WINDOW_1M,),
        cross_features=cross_features,
        provenance={"price_context": "test:price"},
    )


def test_correlation_no_relationship_on_exact_zero() -> None:
    cross = CrossFeatureObservation(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        window=WINDOW_1M,
        pair_label="return_pct_vs_taker_delta",
        correlation=0.0,
        sample_count=5,
        status=FeatureStatus(quality=FeatureQuality.VALID, sample_count=5),
    )
    snapshot = _minimal_snapshot({"1m": cross})

    result = PriceFlowRelationshipAnalyst().analyze(snapshot)

    obs = [o for o in result.observations if o.dimension is AnalysisDimension.CORRELATION_RELATIONSHIP]
    assert obs[0].value == CorrelationRelationship.NO_RELATIONSHIP.value


def test_correlation_negative_relationship() -> None:
    cross = CrossFeatureObservation(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        window=WINDOW_1M,
        pair_label="return_pct_vs_taker_delta",
        correlation=-0.8,
        sample_count=5,
        status=FeatureStatus(quality=FeatureQuality.VALID, sample_count=5),
    )
    snapshot = _minimal_snapshot({"1m": cross})

    result = PriceFlowRelationshipAnalyst().analyze(snapshot)

    obs = [o for o in result.observations if o.dimension is AnalysisDimension.CORRELATION_RELATIONSHIP]
    assert obs[0].value == CorrelationRelationship.NEGATIVE_RELATIONSHIP.value


def test_correlation_omitted_when_unavailable() -> None:
    cross = CrossFeatureObservation(
        symbol="BTCUSDT",
        contract_type=ContractType.PERPETUAL,
        window=WINDOW_1M,
        pair_label="return_pct_vs_taker_delta",
        correlation=None,
        sample_count=1,
        status=FeatureStatus(quality=FeatureQuality.UNAVAILABLE, sample_count=1, reasons=["fewer than 3 paired samples"]),
    )
    snapshot = _minimal_snapshot({"1m": cross})

    result = PriceFlowRelationshipAnalyst().analyze(snapshot)

    assert result.status is AnalystOutcome.ABSTAINED
    obs = [o for o in result.observations if o.dimension is AnalysisDimension.CORRELATION_RELATIONSHIP]
    assert obs == []


def test_price_taker_agreement() -> None:
    engine = make_engine(windows=(WINDOW_10S,))
    engine.record_trade(trade(seconds_ago=5, side=OrderSide.BUY, price="100", quantity="1", trade_id=1))
    engine.record_trade(trade(seconds_ago=1, side=OrderSide.BUY, price="105", quantity="1", trade_id=2))
    snapshot = build_snapshot(engine)
    assert snapshot.price_context["10s"].return_pct > 0
    assert snapshot.taker_flow["10s"].delta > 0

    result = PriceFlowRelationshipAnalyst().analyze(snapshot)

    rel = _dim(result, AnalysisDimension.PRICE_TAKER_RELATIONSHIP)
    assert rel[0].value == PriceFlowRelationship.AGREEMENT.value


def test_price_taker_divergence() -> None:
    engine = make_engine(windows=(WINDOW_10S,))
    engine.record_trade(trade(seconds_ago=5, side=OrderSide.SELL, price="100", quantity="5", trade_id=1))
    engine.record_trade(trade(seconds_ago=1, side=OrderSide.SELL, price="105", quantity="1", trade_id=2))
    snapshot = build_snapshot(engine)
    assert snapshot.price_context["10s"].return_pct > 0
    assert snapshot.taker_flow["10s"].delta < 0

    result = PriceFlowRelationshipAnalyst().analyze(snapshot)

    rel = _dim(result, AnalysisDimension.PRICE_TAKER_RELATIONSHIP)
    assert rel[0].value == PriceFlowRelationship.DIVERGENCE.value


def test_price_taker_no_direction_on_zero_return() -> None:
    engine = make_engine(windows=(WINDOW_10S,))
    engine.record_trade(trade(seconds_ago=5, side=OrderSide.BUY, price="100", quantity="1", trade_id=1))
    engine.record_trade(trade(seconds_ago=1, side=OrderSide.SELL, price="100", quantity="1", trade_id=2))
    snapshot = build_snapshot(engine)
    assert snapshot.price_context["10s"].return_pct == Decimal("0")

    result = PriceFlowRelationshipAnalyst().analyze(snapshot)

    rel = _dim(result, AnalysisDimension.PRICE_TAKER_RELATIONSHIP)
    assert rel[0].value == PriceFlowRelationship.NO_DIRECTION.value


def test_price_open_interest_agreement_and_divergence() -> None:
    engine = make_engine(windows=(WINDOW_10S,))
    engine.record_trade(trade(seconds_ago=5, side=OrderSide.BUY, price="100", quantity="1", trade_id=1))
    engine.record_trade(trade(seconds_ago=1, side=OrderSide.BUY, price="105", quantity="1", trade_id=2))
    engine.record_open_interest(open_interest(seconds_ago=90, value="100"))
    engine.record_open_interest(open_interest(seconds_ago=1, value="110"))
    snapshot = build_snapshot(engine)
    assert snapshot.price_context["10s"].return_pct > 0
    assert snapshot.open_interest.windows["10s"].percent_change > 0

    result = PriceFlowRelationshipAnalyst().analyze(snapshot)
    rel = _dim(result, AnalysisDimension.PRICE_OPEN_INTEREST_RELATIONSHIP)
    assert rel[0].value == PriceFlowRelationship.AGREEMENT.value

    engine2 = make_engine(windows=(WINDOW_10S,))
    engine2.record_trade(trade(seconds_ago=5, side=OrderSide.BUY, price="100", quantity="1", trade_id=1))
    engine2.record_trade(trade(seconds_ago=1, side=OrderSide.BUY, price="105", quantity="1", trade_id=2))
    engine2.record_open_interest(open_interest(seconds_ago=90, value="100"))
    engine2.record_open_interest(open_interest(seconds_ago=1, value="90"))
    snapshot2 = build_snapshot(engine2)
    assert snapshot2.open_interest.windows["10s"].percent_change < 0

    result2 = PriceFlowRelationshipAnalyst().analyze(snapshot2)
    rel2 = _dim(result2, AnalysisDimension.PRICE_OPEN_INTEREST_RELATIONSHIP)
    assert rel2[0].value == PriceFlowRelationship.DIVERGENCE.value


def test_price_liquidation_agreement_and_divergence() -> None:
    engine = make_engine(windows=(WINDOW_10S,))
    engine.record_trade(trade(seconds_ago=5, side=OrderSide.BUY, price="100", quantity="1", trade_id=1))
    engine.record_trade(trade(seconds_ago=1, side=OrderSide.BUY, price="105", quantity="1", trade_id=2))
    engine.record_liquidation(liquidation(seconds_ago=1, side=OrderSide.SELL, quantity="5"))  # long liquidations -> positive imbalance
    snapshot = build_snapshot(engine)
    assert snapshot.price_context["10s"].return_pct > 0
    assert snapshot.liquidation["10s"].liquidation_imbalance > 0

    result = PriceFlowRelationshipAnalyst().analyze(snapshot)
    rel = _dim(result, AnalysisDimension.PRICE_LIQUIDATION_RELATIONSHIP)
    assert rel[0].value == PriceFlowRelationship.AGREEMENT.value

    engine2 = make_engine(windows=(WINDOW_10S,))
    engine2.record_trade(trade(seconds_ago=5, side=OrderSide.BUY, price="100", quantity="1", trade_id=1))
    engine2.record_trade(trade(seconds_ago=1, side=OrderSide.BUY, price="105", quantity="1", trade_id=2))
    engine2.record_liquidation(liquidation(seconds_ago=1, side=OrderSide.BUY, quantity="5"))  # short liquidations -> negative imbalance
    snapshot2 = build_snapshot(engine2)
    assert snapshot2.liquidation["10s"].liquidation_imbalance < 0

    result2 = PriceFlowRelationshipAnalyst().analyze(snapshot2)
    rel2 = _dim(result2, AnalysisDimension.PRICE_LIQUIDATION_RELATIONSHIP)
    assert rel2[0].value == PriceFlowRelationship.DIVERGENCE.value


def test_full_abstention_with_no_windows_configured() -> None:
    engine = make_engine(windows=())
    snapshot = build_snapshot(engine)

    result = PriceFlowRelationshipAnalyst().analyze(snapshot)

    assert result.status is AnalystOutcome.ABSTAINED
    assert result.quality is FeatureQuality.UNAVAILABLE
    assert len(result.abstention_reasons) >= 1


def test_evidence_and_multi_domain_provenance() -> None:
    engine = make_engine(windows=(WINDOW_10S,))
    engine.record_trade(trade(seconds_ago=5, side=OrderSide.BUY, price="100", quantity="1", trade_id=1))
    engine.record_trade(trade(seconds_ago=1, side=OrderSide.BUY, price="105", quantity="1", trade_id=2))
    snapshot = build_snapshot(engine)

    result = PriceFlowRelationshipAnalyst().analyze(snapshot)

    feature_names = {e.feature_name for e in result.evidence}
    assert "price_context.return_pct" in feature_names
    assert "taker_flow.delta" in feature_names
    assert result.provenance.get("price_context") == snapshot.provenance.get("price_context")
    for observation in result.observations:
        for ref in observation.evidence_refs:
            assert 0 <= ref < len(result.evidence)


def test_no_reversal_or_confirmation_vocabulary() -> None:
    forbidden = {"REVERSAL", "CONFIRMATION", "CONFIRMS", "SIGNAL"}
    assert forbidden.isdisjoint(member.value for member in PriceFlowRelationship)
    assert forbidden.isdisjoint(member.value for member in CorrelationRelationship)


def test_multi_symbol_no_leakage() -> None:
    analyst = PriceFlowRelationshipAnalyst()
    engine = make_engine(windows=(WINDOW_10S,))
    engine.record_trade(trade("BTCUSDT", seconds_ago=5, side=OrderSide.BUY, price="100", quantity="1", trade_id=1))
    engine.record_trade(trade("BTCUSDT", seconds_ago=1, side=OrderSide.BUY, price="105", quantity="1", trade_id=2))
    engine.record_trade(trade("ETHUSDT", seconds_ago=5, side=OrderSide.SELL, price="100", quantity="5", trade_id=1))
    engine.record_trade(trade("ETHUSDT", seconds_ago=1, side=OrderSide.SELL, price="105", quantity="1", trade_id=2))

    btc = analyst.analyze(build_snapshot(engine, symbol="BTCUSDT"))
    eth = analyst.analyze(build_snapshot(engine, symbol="ETHUSDT"))

    assert _dim(btc, AnalysisDimension.PRICE_TAKER_RELATIONSHIP)[0].value == PriceFlowRelationship.AGREEMENT.value
    assert _dim(eth, AnalysisDimension.PRICE_TAKER_RELATIONSHIP)[0].value == PriceFlowRelationship.DIVERGENCE.value
