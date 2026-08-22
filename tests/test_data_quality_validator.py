"""DataQualityValidator verdicts."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from app.core.enums import Timeframe
from app.core.models import OHLCVCandle
from app.market_data.exceptions import UnsupportedTimeframeError
from app.market_data.provenance import MarketDataProvenance, MarketDataSource
from app.market_data.timeframes import TIMEFRAME_DURATIONS, timeframe_duration
from app.market_data.validators import DataQualityValidator


@pytest.fixture
def validator() -> DataQualityValidator:
    return DataQualityValidator()


def _provenance(
    now: datetime,
    source: MarketDataSource = MarketDataSource.KLINES,
    timeframe: Timeframe | None = Timeframe.M5,
) -> MarketDataProvenance:
    return MarketDataProvenance(
        provider="binance",
        source=source,
        symbol="BTCUSDT",
        timeframe=timeframe,
        fetched_at=now,
    )


def _candle(timestamp: datetime) -> OHLCVCandle:
    return OHLCVCandle(
        timestamp=timestamp,
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal("100.5"),
        volume=Decimal("10"),
    )


def _series(latest: datetime, count: int = 3, step: timedelta = timedelta(minutes=5)) -> list[
    OHLCVCandle
]:
    return [_candle(latest - step * offset) for offset in reversed(range(count))]


# --------------------------------------------------------------------------- #
# candles
# --------------------------------------------------------------------------- #


def test_fresh_ordered_series_is_valid(validator: DataQualityValidator, now: datetime) -> None:
    quality = validator.validate_candles(
        _series(now), provenance=_provenance(now), timeframe=Timeframe.M5, now=now
    )
    assert quality.is_valid
    assert not quality.is_stale
    assert quality.warnings == []
    assert quality.source == "binance:klines"
    assert quality.checked_at == now


def test_empty_series_is_invalid(validator: DataQualityValidator, now: datetime) -> None:
    quality = validator.validate_candles([], provenance=_provenance(now), now=now)
    assert not quality.is_valid
    assert quality.is_stale
    assert quality.missing_data == ["ohlcv"]
    assert "empty OHLCV result" in quality.warnings


def test_duplicate_timestamps_are_invalid(
    validator: DataQualityValidator, now: datetime
) -> None:
    candles = [_candle(now - timedelta(minutes=5)), _candle(now), _candle(now)]
    quality = validator.validate_candles(
        candles, provenance=_provenance(now), timeframe=Timeframe.M5, now=now
    )
    assert not quality.is_valid
    assert "duplicate candle timestamps" in quality.warnings


def test_unsorted_series_is_invalid(validator: DataQualityValidator, now: datetime) -> None:
    candles = [_candle(now), _candle(now - timedelta(minutes=5))]
    quality = validator.validate_candles(
        candles, provenance=_provenance(now), timeframe=Timeframe.M5, now=now
    )
    assert not quality.is_valid
    assert "candles are not ordered by ascending time" in quality.warnings


def test_stale_latest_candle_is_flagged(validator: DataQualityValidator, now: datetime) -> None:
    stale_series = _series(now - timedelta(minutes=30))
    quality = validator.validate_candles(
        stale_series, provenance=_provenance(now), timeframe=Timeframe.M5, now=now
    )
    assert quality.is_valid  # structurally fine, just old
    assert quality.is_stale
    assert any("stale" in warning or "old" in warning for warning in quality.warnings)


def test_still_forming_candle_is_not_stale(
    validator: DataQualityValidator, now: datetime
) -> None:
    quality = validator.validate_candles(
        _series(now - timedelta(minutes=4)),
        provenance=_provenance(now),
        timeframe=Timeframe.M5,
        now=now,
    )
    assert not quality.is_stale


def test_staleness_tolerance_is_configurable(now: datetime) -> None:
    series = _series(now - timedelta(minutes=6))
    assert DataQualityValidator(staleness_tolerance=0.0).validate_candles(
        series, provenance=_provenance(now), timeframe=Timeframe.M5, now=now
    ).is_stale
    assert not DataQualityValidator(staleness_tolerance=1.0).validate_candles(
        series, provenance=_provenance(now), timeframe=Timeframe.M5, now=now
    ).is_stale


def test_negative_tolerance_is_rejected() -> None:
    with pytest.raises(ValueError, match="must not be negative"):
        DataQualityValidator(staleness_tolerance=-1.0)


def test_timeframe_falls_back_to_provenance(
    validator: DataQualityValidator, now: datetime
) -> None:
    quality = validator.validate_candles(
        _series(now - timedelta(hours=3)),
        provenance=_provenance(now, timeframe=Timeframe.H1),
        now=now,
    )
    assert quality.is_stale


def test_unknown_timeframe_skips_staleness(
    validator: DataQualityValidator, now: datetime
) -> None:
    quality = validator.validate_candles(
        _series(now - timedelta(days=400)),
        provenance=_provenance(now, timeframe=None),
        now=now,
    )
    assert quality.is_valid
    assert not quality.is_stale
    assert quality.missing_data == ["timeframe"]


# --------------------------------------------------------------------------- #
# bid / ask
# --------------------------------------------------------------------------- #


def test_valid_bid_ask(validator: DataQualityValidator, now: datetime) -> None:
    quality = validator.validate_bid_ask(
        Decimal("100"),
        Decimal("100.5"),
        provenance=_provenance(now, MarketDataSource.BOOK_TICKER, None),
        now=now,
    )
    assert quality.is_valid
    assert quality.source == "binance:book_ticker"


def test_crossed_bid_ask_is_invalid(validator: DataQualityValidator, now: datetime) -> None:
    quality = validator.validate_bid_ask(
        Decimal("101"),
        Decimal("100"),
        provenance=_provenance(now, MarketDataSource.BOOK_TICKER, None),
        now=now,
    )
    assert not quality.is_valid
    assert "ask 100 is below bid 101" in quality.warnings


def test_negative_bid_ask_is_invalid(validator: DataQualityValidator, now: datetime) -> None:
    quality = validator.validate_bid_ask(
        Decimal("-1"),
        Decimal("1"),
        provenance=_provenance(now, MarketDataSource.BOOK_TICKER, None),
        now=now,
    )
    assert not quality.is_valid
    assert any("negative quote" in warning for warning in quality.warnings)


# --------------------------------------------------------------------------- #
# symbol
# --------------------------------------------------------------------------- #


def test_matching_symbol_is_valid(validator: DataQualityValidator, now: datetime) -> None:
    quality = validator.validate_symbol(
        expected="BTCUSDT", received="BTCUSDT", provenance=_provenance(now), now=now
    )
    assert quality.is_valid


def test_mismatched_symbol_is_invalid(validator: DataQualityValidator, now: datetime) -> None:
    quality = validator.validate_symbol(
        expected="BTCUSDT", received="ETHUSDT", provenance=_provenance(now), now=now
    )
    assert not quality.is_valid
    assert "does not match requested" in quality.warnings[0]


def test_absent_symbol_is_invalid(validator: DataQualityValidator, now: datetime) -> None:
    quality = validator.validate_symbol(
        expected="BTCUSDT", received=None, provenance=_provenance(now), now=now
    )
    assert not quality.is_valid
    assert quality.missing_data == ["symbol"]


# --------------------------------------------------------------------------- #
# timeframe durations
# --------------------------------------------------------------------------- #


def test_every_timeframe_has_a_duration() -> None:
    assert set(TIMEFRAME_DURATIONS) == set(Timeframe)


def test_timeframe_duration_lookup() -> None:
    assert timeframe_duration(Timeframe.H4) == timedelta(hours=4)


def test_timeframe_duration_rejects_unknown_value() -> None:
    with pytest.raises(UnsupportedTimeframeError):
        timeframe_duration("M7")  # type: ignore[arg-type]
