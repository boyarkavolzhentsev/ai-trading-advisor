"""System-wide contract constants.

These are contract-level facts, not tunable strategy parameters. Anything that
can vary per account or per cycle belongs in a configuration model instead.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Final

from app.core.enums.market import Timeframe

SIGNAL_EXECUTION_WINDOW: Final[timedelta] = timedelta(minutes=5)
"""Execution window of a LONG/SHORT recommendation.

``valid_until`` of a setup is ``signal_time + SIGNAL_EXECUTION_WINDOW``.
Expiry handling is not implemented yet.
"""

SETUP_STRUCTURE_TIMEFRAME: Final[Timeframe] = Timeframe.M15
"""Authoritative ``TechnicalFeatureSnapshot`` timeframe for Setup
Construction's structural stop-loss rules (TREND_FOLLOWING swings, BREAKOUT
structural breaks) - an explicit V1 trading-policy decision, not inferred
from existing repository behavior. No timeframe fallback is implemented: if
the M15 ``MarketStructureFeatures`` block is unavailable or below approved
quality this cycle, Setup Construction fails closed rather than substituting
another timeframe.
"""
