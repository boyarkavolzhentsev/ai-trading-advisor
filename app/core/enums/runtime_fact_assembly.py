"""Runtime Fact Assembly vocabulary.

Describes only the outcome/reason space of assembling one Stage 7
``AccountRiskSnapshot`` from three already-produced, independently-authoritative
Stage 10B/10C/10D assessments (``MT5RolloverSnapshot``,
``MT5RealizedDailyPnLAssessment``, ``MT5OpenRiskAssessment``) - never a new
financial computation, never a trade recommendation, never MT5 connectivity
state (that remains ``MT5ConnectivityState``'s exclusive vocabulary).
"""

from __future__ import annotations

from enum import StrEnum


class RuntimeFactAssemblyOutcome(StrEnum):
    """Coarse result of one ``AccountRiskSnapshot`` assembly attempt."""

    READY = "READY"
    BLOCKED = "BLOCKED"


class RuntimeFactAssemblyBlockReason(StrEnum):
    """Why one assembly attempt could not produce an ``AccountRiskSnapshot``.

    ``ROLLOVER_UNAVAILABLE``/``REALIZED_PNL_UNAVAILABLE``/
    ``OPEN_RISK_UNAVAILABLE`` each mirror their own upstream Stage 10B/10D/10C
    assessment's own fail-closed outcome - never a fabricated substitute
    value. ``TIMESTAMP_MISMATCH`` covers both the caller-supplied ``as_of``
    disagreeing with any of the three upstream assessments' own ``as_of``,
    and the rollover state's ``trading_day_key`` disagreeing with the
    realized-PnL assessment's own ``trading_day_key`` - both are the same
    underlying risk: the three facts no longer describe one coherent runtime
    cycle.
    """

    ROLLOVER_UNAVAILABLE = "ROLLOVER_UNAVAILABLE"
    REALIZED_PNL_UNAVAILABLE = "REALIZED_PNL_UNAVAILABLE"
    OPEN_RISK_UNAVAILABLE = "OPEN_RISK_UNAVAILABLE"
    TIMESTAMP_MISMATCH = "TIMESTAMP_MISMATCH"


__all__ = ["RuntimeFactAssemblyBlockReason", "RuntimeFactAssemblyOutcome"]
