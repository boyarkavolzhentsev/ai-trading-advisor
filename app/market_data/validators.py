"""Deterministic market data quality checks.

The validator judges normalized data and emits a ``DataQuality`` verdict. It
never repairs, fills, reorders or drops anything: callers decide how to react
to a negative verdict.

Verdict semantics:

- ``is_valid=False`` — the data is unusable as delivered.
- ``is_stale=True`` — the data is structurally fine but too old to be trusted;
  downstream components may degrade instead of rejecting it.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal

from app.core.enums.market import Timeframe
from app.core.models.candle import OHLCVCandle
from app.core.models.data_quality import DataQuality
from app.market_data.provenance import MarketDataProvenance
from app.market_data.timeframes import timeframe_duration

DEFAULT_STALENESS_TOLERANCE = 1.0
"""Extra candle durations allowed on top of the still-forming candle.

The latest candle of a series has just opened, so its timestamp legitimately
lags "now" by up to one full duration. Tolerance ``1.0`` therefore accepts an
age of up to two durations before flagging staleness.
"""


def _utc_now() -> datetime:
    return datetime.now(UTC)


class DataQualityValidator:
    """Stateless, deterministic validator of normalized market data."""

    def __init__(self, staleness_tolerance: float = DEFAULT_STALENESS_TOLERANCE) -> None:
        if staleness_tolerance < 0:
            raise ValueError("staleness_tolerance must not be negative")
        self._staleness_tolerance = staleness_tolerance

    def validate_candles(
        self,
        candles: Sequence[OHLCVCandle],
        *,
        provenance: MarketDataProvenance,
        timeframe: Timeframe | None = None,
        now: datetime | None = None,
    ) -> DataQuality:
        """Check series-level integrity of an OHLCV result.

        Per-candle integrity (price ranges, signs, awareness of the timestamp)
        is already enforced by ``OHLCVCandle``. This checks what a single
        candle cannot know: emptiness, ordering, duplicates and staleness.
        """
        checked_at = now or _utc_now()
        timeframe = timeframe if timeframe is not None else provenance.timeframe

        if not candles:
            return DataQuality(
                is_valid=False,
                is_stale=True,
                missing_data=["ohlcv"],
                warnings=["empty OHLCV result"],
                source=provenance.label,
                checked_at=checked_at,
            )

        warnings: list[str] = []
        missing: list[str] = []
        is_valid = True
        is_stale = False

        timestamps = [candle.timestamp for candle in candles]

        if len(set(timestamps)) != len(timestamps):
            is_valid = False
            warnings.append("duplicate candle timestamps")

        if any(later < earlier for earlier, later in zip(timestamps, timestamps[1:])):
            is_valid = False
            warnings.append("candles are not ordered by ascending time")

        if timeframe is None:
            missing.append("timeframe")
            warnings.append("staleness not checked: timeframe unknown")
        else:
            max_age = timeframe_duration(timeframe) * (1 + self._staleness_tolerance)
            age = checked_at - max(timestamps)
            if age > max_age:
                is_stale = True
                warnings.append(f"latest candle is {age} old, tolerance is {max_age}")

        return DataQuality(
            is_valid=is_valid,
            is_stale=is_stale,
            missing_data=missing,
            warnings=warnings,
            source=provenance.label,
            checked_at=checked_at,
        )

    def validate_bid_ask(
        self,
        bid: Decimal,
        ask: Decimal,
        *,
        provenance: MarketDataProvenance,
        now: datetime | None = None,
    ) -> DataQuality:
        """Check the bid/ask relationship before a quote model is built."""
        checked_at = now or _utc_now()
        warnings: list[str] = []

        if bid < 0 or ask < 0:
            warnings.append(f"negative quote: bid={bid} ask={ask}")
        if ask < bid:
            warnings.append(f"ask {ask} is below bid {bid}")

        return DataQuality(
            is_valid=not warnings,
            warnings=warnings,
            source=provenance.label,
            checked_at=checked_at,
        )

    def validate_symbol(
        self,
        *,
        expected: str,
        received: str | None,
        provenance: MarketDataProvenance,
        now: datetime | None = None,
    ) -> DataQuality:
        """Check that a response describes the instrument that was requested."""
        checked_at = now or _utc_now()
        warnings: list[str] = []
        missing: list[str] = []

        if received is None:
            missing.append("symbol")
            warnings.append("response carries no symbol")
        elif received != expected:
            warnings.append(f"response symbol {received!r} does not match requested {expected!r}")

        return DataQuality(
            is_valid=not warnings,
            missing_data=missing,
            warnings=warnings,
            source=provenance.label,
            checked_at=checked_at,
        )


__all__ = ["DEFAULT_STALENESS_TOLERANCE", "DataQualityValidator"]
