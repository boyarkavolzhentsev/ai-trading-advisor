"""System-wide contract constants.

These are contract-level facts, not tunable strategy parameters. Anything that
can vary per account or per cycle belongs in a configuration model instead.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Final

SIGNAL_EXECUTION_WINDOW: Final[timedelta] = timedelta(minutes=5)
"""Execution window of a LONG/SHORT recommendation.

``valid_until`` of a setup is ``signal_time + SIGNAL_EXECUTION_WINDOW``.
Expiry handling is not implemented yet.
"""
