"""Default technical-contour timeframe preset (Stage 3A).

Configuration preset only - never referenced positionally by any calculator
or by ``TechnicalFeatureEngine`` in this package (every method takes an
explicit ``Timeframe`` parameter). ``M30`` and ``W1`` remain fully
supported - ``Timeframe``/``timeframe_duration`` already cover them - but
are intentionally excluded from this default set pending an approved need
for them in the default technical contour.
"""

from __future__ import annotations

from app.core.enums.market import Timeframe

DEFAULT_TECHNICAL_TIMEFRAMES: tuple[Timeframe, ...] = (
    Timeframe.M1,
    Timeframe.M5,
    Timeframe.M15,
    Timeframe.H1,
    Timeframe.H4,
    Timeframe.D1,
)
"""Approved default technical contour. Configurable defaults only."""

__all__ = ["DEFAULT_TECHNICAL_TIMEFRAMES"]
