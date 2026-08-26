"""Shared ``TechnicalFeatureSnapshot`` builders for Stage 3B analyst tests.

Feature blocks are constructed directly (not derived from candles through
the real Stage 3A calculators) so each test can pin exact numeric facts
(zero, midpoint, boundary values) without reverse-engineering candle
arithmetic - Stage 3A's own arithmetic is already covered by
``tests/test_technical_*.py``. Not a test module itself (no ``test_``
prefix): pytest will not collect it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.core.enums.instrument import ContractType
from app.core.enums.market import Timeframe
from app.core.enums.quality import FeatureQuality
from app.core.enums.technical import BreakDirection, SwingKind
from app.core.models.candle_structure_features import CandleStructureFeatures
from app.core.models.feature_status import FeatureStatus
from app.core.models.market_structure_features import MarketStructureFeatures, StructuralBreak, SwingPoint
from app.core.models.momentum_features import MomentumFeatures
from app.core.models.moving_average_features import MovingAverageFeatures
from app.core.models.range_state_features import RangeStateFeatures
from app.core.models.technical_feature_snapshot import TechnicalFeatureSnapshot
from app.core.models.trend_features import TrendFeatures
from app.core.models.volatility_features import VolatilityFeatures

SYMBOL = "BTCUSDT"
NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
SOURCE = "test"


def status(
    quality: FeatureQuality = FeatureQuality.VALID, *, sample_count: int = 10, reasons: tuple[str, ...] = ()
) -> FeatureStatus:
    return FeatureStatus(quality=quality, sample_count=sample_count, reasons=list(reasons))


def make_trend(
    *,
    return_pct: Decimal | None = Decimal("0"),
    slope: Decimal | None = Decimal("0"),
    higher_high_count: int = 0,
    higher_low_count: int = 0,
    lower_high_count: int = 0,
    lower_low_count: int = 0,
    directional_persistence: Decimal | None = None,
    block_status: FeatureStatus | None = None,
    symbol: str = SYMBOL,
    contract_type: ContractType = ContractType.PERPETUAL,
    timeframe: Timeframe = Timeframe.M1,
    lookback: int = 20,
    source: str = SOURCE,
) -> TrendFeatures:
    return TrendFeatures(
        symbol=symbol,
        contract_type=contract_type,
        timeframe=timeframe,
        lookback=lookback,
        return_pct=return_pct,
        slope=slope,
        higher_high_count=higher_high_count,
        higher_low_count=higher_low_count,
        lower_high_count=lower_high_count,
        lower_low_count=lower_low_count,
        directional_persistence=directional_persistence,
        status=block_status or status(),
        source=source,
    )


def make_swing(
    *,
    kind: SwingKind = SwingKind.HIGH,
    candle_time: datetime,
    price: Decimal = Decimal("100"),
    confirmed_at: datetime,
    left_bars: int = 2,
    right_bars: int = 2,
) -> SwingPoint:
    return SwingPoint(
        kind=kind, candle_time=candle_time, price=price, confirmed_at=confirmed_at,
        left_bars=left_bars, right_bars=right_bars,
    )


def make_break(
    *, direction: BreakDirection, swing: SwingPoint, break_candle_time: datetime, break_close: Decimal
) -> StructuralBreak:
    return StructuralBreak(
        direction=direction, broken_swing=swing, break_candle_time=break_candle_time,
        break_close=break_close, confirmed_at=break_candle_time,
    )


def make_market_structure(
    *,
    swings: tuple[SwingPoint, ...] = (),
    breaks: tuple[StructuralBreak, ...] = (),
    block_status: FeatureStatus | None = None,
    symbol: str = SYMBOL,
    contract_type: ContractType = ContractType.PERPETUAL,
    timeframe: Timeframe = Timeframe.M1,
    left_bars: int = 2,
    right_bars: int = 2,
    source: str = SOURCE,
) -> MarketStructureFeatures:
    return MarketStructureFeatures(
        symbol=symbol, contract_type=contract_type, timeframe=timeframe,
        left_bars=left_bars, right_bars=right_bars, swings=swings, breaks=breaks,
        status=block_status or status(), source=source,
    )


def make_volatility(
    *,
    true_range: Decimal | None = Decimal("2"),
    atr: Decimal | None = Decimal("2"),
    realized_volatility: Decimal | None = None,
    rolling_range: Decimal | None = Decimal("2"),
    range_expansion_ratio: Decimal | None = Decimal("1"),
    block_status: FeatureStatus | None = None,
    symbol: str = SYMBOL,
    contract_type: ContractType = ContractType.PERPETUAL,
    timeframe: Timeframe = Timeframe.M1,
    atr_period: int = 14,
    volatility_lookback: int = 20,
    source: str = SOURCE,
) -> VolatilityFeatures:
    return VolatilityFeatures(
        symbol=symbol, contract_type=contract_type, timeframe=timeframe,
        atr_period=atr_period, volatility_lookback=volatility_lookback,
        true_range=true_range, atr=atr, realized_volatility=realized_volatility,
        rolling_range=rolling_range, range_expansion_ratio=range_expansion_ratio,
        status=block_status or status(), source=source,
    )


def make_momentum(
    *,
    roc: Decimal | None = Decimal("0"),
    rsi: Decimal | None = Decimal("50"),
    block_status: FeatureStatus | None = None,
    symbol: str = SYMBOL,
    contract_type: ContractType = ContractType.PERPETUAL,
    timeframe: Timeframe = Timeframe.M1,
    roc_period: int = 12,
    rsi_period: int = 14,
    source: str = SOURCE,
) -> MomentumFeatures:
    return MomentumFeatures(
        symbol=symbol, contract_type=contract_type, timeframe=timeframe,
        roc_period=roc_period, rsi_period=rsi_period, roc=roc, rsi=rsi,
        status=block_status or status(), source=source,
    )


def make_moving_average(
    *,
    periods: tuple[int, ...] = (20, 50),
    sma: dict[int, Decimal] | None = None,
    ema: dict[int, Decimal] | None = None,
    distance_from_sma_pct: dict[int, Decimal] | None = None,
    ma_slope: dict[int, Decimal] | None = None,
    block_status: FeatureStatus | None = None,
    symbol: str = SYMBOL,
    contract_type: ContractType = ContractType.PERPETUAL,
    timeframe: Timeframe = Timeframe.M1,
    source: str = SOURCE,
) -> MovingAverageFeatures:
    return MovingAverageFeatures(
        symbol=symbol, contract_type=contract_type, timeframe=timeframe, periods=periods,
        sma=sma if sma is not None else {20: Decimal("105"), 50: Decimal("100")},
        ema=ema if ema is not None else {20: Decimal("105"), 50: Decimal("100")},
        distance_from_sma_pct=distance_from_sma_pct if distance_from_sma_pct is not None else {
            20: Decimal("1"), 50: Decimal("2")
        },
        ma_slope=ma_slope if ma_slope is not None else {20: Decimal("1"), 50: Decimal("1")},
        status=block_status or status(), source=source,
    )


def make_candle_structure(
    *,
    candle_time: datetime | None = NOW,
    body_size: Decimal | None = Decimal("1"),
    upper_wick: Decimal | None = Decimal("1"),
    lower_wick: Decimal | None = Decimal("1"),
    range_size: Decimal | None = Decimal("3"),
    body_to_range_ratio: Decimal | None = Decimal("1") / Decimal("3"),
    close_location_value: Decimal | None = Decimal("0.5"),
    block_status: FeatureStatus | None = None,
    symbol: str = SYMBOL,
    contract_type: ContractType = ContractType.PERPETUAL,
    timeframe: Timeframe = Timeframe.M1,
    source: str = SOURCE,
) -> CandleStructureFeatures:
    return CandleStructureFeatures(
        symbol=symbol, contract_type=contract_type, timeframe=timeframe, candle_time=candle_time,
        body_size=body_size, upper_wick=upper_wick, lower_wick=lower_wick, range_size=range_size,
        body_to_range_ratio=body_to_range_ratio, close_location_value=close_location_value,
        status=block_status or status(sample_count=1), source=source,
    )


def make_range_state(
    *,
    rolling_range: Decimal | None = Decimal("2"),
    normalized_range: Decimal | None = Decimal("1"),
    directional_efficiency: Decimal | None = Decimal("1"),
    block_status: FeatureStatus | None = None,
    symbol: str = SYMBOL,
    contract_type: ContractType = ContractType.PERPETUAL,
    timeframe: Timeframe = Timeframe.M1,
    lookback: int = 20,
    atr_period: int = 14,
    source: str = SOURCE,
) -> RangeStateFeatures:
    return RangeStateFeatures(
        symbol=symbol, contract_type=contract_type, timeframe=timeframe, lookback=lookback,
        atr_period=atr_period, rolling_range=rolling_range, normalized_range=normalized_range,
        directional_efficiency=directional_efficiency, status=block_status or status(), source=source,
    )


def make_snapshot(
    *,
    trend: TrendFeatures | None = None,
    market_structure: MarketStructureFeatures | None = None,
    volatility: VolatilityFeatures | None = None,
    momentum: MomentumFeatures | None = None,
    moving_average: MovingAverageFeatures | None = None,
    candle_structure: CandleStructureFeatures | None = None,
    range_state: RangeStateFeatures | None = None,
    symbol: str = SYMBOL,
    contract_type: ContractType = ContractType.PERPETUAL,
    timeframe: Timeframe = Timeframe.M1,
    observation_time: datetime = NOW,
    last_closed_candle_time: datetime | None = None,
    source: str = SOURCE,
) -> TechnicalFeatureSnapshot:
    """Build one internally consistent snapshot; every block defaults to a
    simple VALID/neutral fact so a test need only override the block(s) it
    is exercising."""
    if last_closed_candle_time is None:
        last_closed_candle_time = observation_time - timedelta(minutes=1)

    return TechnicalFeatureSnapshot(
        symbol=symbol,
        contract_type=contract_type,
        timeframe=timeframe,
        observation_time=observation_time,
        last_closed_candle_time=last_closed_candle_time,
        live_candle=None,
        trend=trend if trend is not None else make_trend(symbol=symbol, contract_type=contract_type, timeframe=timeframe),
        market_structure=market_structure
        if market_structure is not None
        else make_market_structure(symbol=symbol, contract_type=contract_type, timeframe=timeframe),
        volatility=volatility
        if volatility is not None
        else make_volatility(symbol=symbol, contract_type=contract_type, timeframe=timeframe),
        momentum=momentum
        if momentum is not None
        else make_momentum(symbol=symbol, contract_type=contract_type, timeframe=timeframe),
        moving_average=moving_average
        if moving_average is not None
        else make_moving_average(symbol=symbol, contract_type=contract_type, timeframe=timeframe),
        candle_structure=candle_structure
        if candle_structure is not None
        else make_candle_structure(symbol=symbol, contract_type=contract_type, timeframe=timeframe),
        range_state=range_state
        if range_state is not None
        else make_range_state(symbol=symbol, contract_type=contract_type, timeframe=timeframe),
        status=status(),
        source=source,
    )


__all__ = [
    "NOW",
    "SOURCE",
    "SYMBOL",
    "make_break",
    "make_candle_structure",
    "make_market_structure",
    "make_momentum",
    "make_moving_average",
    "make_range_state",
    "make_snapshot",
    "make_swing",
    "make_trend",
    "make_volatility",
    "status",
]
