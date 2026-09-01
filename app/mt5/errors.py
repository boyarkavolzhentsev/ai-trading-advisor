"""Stage 10A client-misuse errors.

Every error here signals a programmer/orchestration mistake in how
``MT5Client`` was called - never a legitimate broker/runtime condition (that
legitimate case is always a typed ``MT5ConnectivityState`` value returned
from ``initialize()``/``runtime_status()``, never an exception). Mirrors
``app.risk.errors`` one architectural layer over: expected account/runtime
states are results, not exceptions; only caller-contract violations raise.
"""

from __future__ import annotations


class MT5ClientError(RuntimeError):
    """Base class for all Stage 10A client-contract violations."""


class MT5NotInitializedError(MT5ClientError):
    """Raised when an initialized-only operation (e.g. ``account_facts()``)
    is invoked before ``initialize()`` has ever succeeded, or after
    ``shutdown()`` - never for a legitimate broker/terminal/account
    condition, which is always surfaced as an ``MT5ConnectivityState``
    instead."""


__all__ = ["MT5ClientError", "MT5NotInitializedError"]
