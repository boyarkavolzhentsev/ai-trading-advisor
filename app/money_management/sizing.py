"""Stage 7 pure position-sizing calculator.

A narrow, deterministic, stateless function of exactly two already-computed
monetary facts - never reads Policy/Judge/Router output, account state, or
``TradingCycleConfig`` itself (those are ``app.risk.engine``'s job), performs
no broker lot-step/tick rounding, no portfolio allocation, and no I/O.
"""

from __future__ import annotations

from decimal import Decimal


def calculate_recommended_units(*, max_individual_risk: Decimal, risk_per_unit: Decimal) -> Decimal:
    """Generic unit count affordable at ``max_individual_risk`` given
    ``risk_per_unit`` - caller guarantees ``risk_per_unit > 0``."""
    return max_individual_risk / risk_per_unit


__all__ = ["calculate_recommended_units"]
