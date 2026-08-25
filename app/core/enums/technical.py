"""Stage 3A technical/market-structure enums - deterministic geometry only.

No member here is a trading instruction or a trend-state judgement
(no BULLISH/BEARISH, no UPTREND/DOWNTREND, no BOS/CHoCH vocabulary):
Stage 3A describes confirmed geometric facts about candle structure only.
Interpreting these facts into a technical "read" is reserved for a later
Stage 3B specialist layer, mirroring the ``app.core.enums.flow_analysis``
boundary one contour over.
"""

from __future__ import annotations

from enum import StrEnum


class SwingKind(StrEnum):
    """Which extreme a confirmed fractal ``SwingPoint`` marks."""

    HIGH = "HIGH"
    LOW = "LOW"


class BreakDirection(StrEnum):
    """Direction of an objective, close-based structural break.

    Deliberately not "bullish"/"bearish" BOS - a structural break is a
    geometric fact about price crossing a prior confirmed swing level, never
    a trading signal.
    """

    UPWARD_BREAK = "UPWARD_BREAK"
    DOWNWARD_BREAK = "DOWNWARD_BREAK"


__all__ = ["BreakDirection", "SwingKind"]
