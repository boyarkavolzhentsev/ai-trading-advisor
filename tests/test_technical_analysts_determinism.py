"""Determinism and isolation guarantees shared by every Stage 3B analyst."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.enums.instrument import ContractType
from app.core.enums.market import Timeframe
from app.technical_analysts.candle_structure import CandleStructureAnalyst
from app.technical_analysts.market_structure import MarketStructureAnalyst
from app.technical_analysts.momentum import MomentumAnalyst
from app.technical_analysts.moving_average import MovingAverageAnalyst
from app.technical_analysts.range_state import RangeStateAnalyst
from app.technical_analysts.trend import TrendAnalyst
from app.technical_analysts.volatility import VolatilityAnalyst
from tests.technical_analysts_support import make_snapshot, make_trend

ANALYST_CLASSES = (
    TrendAnalyst,
    MarketStructureAnalyst,
    VolatilityAnalyst,
    MomentumAnalyst,
    MovingAverageAnalyst,
    CandleStructureAnalyst,
    RangeStateAnalyst,
)


@pytest.mark.parametrize("analyst_cls", ANALYST_CLASSES, ids=lambda c: c.__name__)
def test_repeated_analyze_calls_are_identical(analyst_cls) -> None:
    snapshot = make_snapshot(trend=make_trend(return_pct=Decimal("3"), slope=Decimal("1")))
    analyst = analyst_cls()
    first = analyst.analyze(snapshot)
    second = analyst.analyze(snapshot)
    assert first == second


@pytest.mark.parametrize("analyst_cls", ANALYST_CLASSES, ids=lambda c: c.__name__)
def test_analyst_has_no_instance_state_after_construction(analyst_cls) -> None:
    instance = analyst_cls()
    assert vars(instance) == {}


@pytest.mark.parametrize("analyst_cls", ANALYST_CLASSES, ids=lambda c: c.__name__)
def test_analyze_does_not_mutate_the_snapshot(analyst_cls) -> None:
    snapshot = make_snapshot(trend=make_trend(return_pct=Decimal("3"), slope=Decimal("1")))
    before = snapshot.model_dump()
    analyst_cls().analyze(snapshot)
    after = snapshot.model_dump()
    assert before == after


@pytest.mark.parametrize("analyst_cls", ANALYST_CLASSES, ids=lambda c: c.__name__)
def test_multiple_symbols_do_not_leak_into_each_other(analyst_cls) -> None:
    analyst = analyst_cls()
    btc = make_snapshot(symbol="BTCUSDT", trend=make_trend(return_pct=Decimal("3"), symbol="BTCUSDT"))
    eth = make_snapshot(symbol="ETHUSDT", trend=make_trend(return_pct=Decimal("-3"), symbol="ETHUSDT"))
    btc_result = analyst.analyze(btc)
    eth_result = analyst.analyze(eth)
    assert btc_result.symbol == "BTCUSDT"
    assert eth_result.symbol == "ETHUSDT"
    # re-running BTC after ETH must reproduce the identical BTC result
    assert analyst.analyze(btc) == btc_result


@pytest.mark.parametrize("analyst_cls", ANALYST_CLASSES, ids=lambda c: c.__name__)
def test_spot_and_perpetual_are_isolated(analyst_cls) -> None:
    analyst = analyst_cls()
    spot = make_snapshot(contract_type=ContractType.SPOT, trend=make_trend(contract_type=ContractType.SPOT))
    perpetual = make_snapshot(contract_type=ContractType.PERPETUAL, trend=make_trend(contract_type=ContractType.PERPETUAL))
    spot_result = analyst.analyze(spot)
    perpetual_result = analyst.analyze(perpetual)
    assert spot_result.contract_type is ContractType.SPOT
    assert perpetual_result.contract_type is ContractType.PERPETUAL


@pytest.mark.parametrize("analyst_cls", ANALYST_CLASSES, ids=lambda c: c.__name__)
def test_multiple_timeframes_do_not_leak(analyst_cls) -> None:
    analyst = analyst_cls()
    m1 = make_snapshot(timeframe=Timeframe.M1, trend=make_trend(timeframe=Timeframe.M1))
    h4 = make_snapshot(timeframe=Timeframe.H4, trend=make_trend(timeframe=Timeframe.H4))
    m1_result = analyst.analyze(m1)
    h4_result = analyst.analyze(h4)
    assert m1_result.timeframe is Timeframe.M1
    assert h4_result.timeframe is Timeframe.H4
    assert analyst.analyze(m1) == m1_result


@pytest.mark.parametrize("analyst_cls", ANALYST_CLASSES, ids=lambda c: c.__name__)
def test_no_cross_call_leakage_across_interleaved_calls(analyst_cls) -> None:
    analyst = analyst_cls()
    snapshots = [
        make_snapshot(symbol="BTCUSDT", trend=make_trend(return_pct=Decimal("1"), symbol="BTCUSDT")),
        make_snapshot(symbol="ETHUSDT", trend=make_trend(return_pct=Decimal("2"), symbol="ETHUSDT")),
        make_snapshot(symbol="SOLUSDT", trend=make_trend(return_pct=Decimal("3"), symbol="SOLUSDT")),
    ]
    baseline = [analyst.analyze(s) for s in snapshots]
    interleaved = [analyst.analyze(s) for s in (snapshots[2], snapshots[0], snapshots[1])]
    assert interleaved[0] == baseline[2]
    assert interleaved[1] == baseline[0]
    assert interleaved[2] == baseline[1]
