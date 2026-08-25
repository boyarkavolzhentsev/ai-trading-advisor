"""Stage 3A candle-ingestion errors.

Every error here signals a programming/upstream-data mistake in how candles
were handed to ``TechnicalFeatureEngine`` - never a legitimate market
condition. The engine fails loudly on these rather than disguising them as
a quality degradation (that legitimate case is
``app.core.enums.quality.FeatureQuality.PARTIAL``/``UNAVAILABLE``, which
only ever arises from genuinely insufficient or gapped history - never from
malformed input).
"""

from __future__ import annotations


class TechnicalIngestionError(ValueError):
    """Base class for all Stage 3A candle-ingestion contract violations."""


class DuplicateCandleTimestampError(TechnicalIngestionError):
    """Raised when a candle's timestamp duplicates one already retained for
    the same ``(symbol, contract_type, timeframe)``."""


class MisalignedCandleError(TechnicalIngestionError):
    """Raised when a candle's timestamp does not sit on its timeframe's UTC
    epoch-aligned boundary."""


__all__ = ["DuplicateCandleTimestampError", "MisalignedCandleError", "TechnicalIngestionError"]
