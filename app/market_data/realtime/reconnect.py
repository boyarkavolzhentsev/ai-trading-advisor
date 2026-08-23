"""Reconnect backoff policy.

Pure and deterministic: no sleeping, no randomness sampled internally, no
provider knowledge. The transport calls this to compute a delay and supplies
its own jitter draw, keeping the policy trivially unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReconnectPolicy:
    """Exponential backoff with full jitter.

    ``delay_for_attempt`` returns ``min(base * factor**(attempt-1), max) *
    jitter``. Passing ``jitter=1.0`` (from the caller's random source) would
    give the uncapped-but-ceiling-bound delay; real callers draw
    ``jitter`` from ``[0, 1)`` so restarts spread out rather than
    synchronizing (avoids a reconnect thundering herd).
    """

    base_seconds: float = 1.0
    factor: float = 2.0
    max_seconds: float = 60.0

    def __post_init__(self) -> None:
        if self.base_seconds <= 0:
            raise ValueError("base_seconds must be positive")
        if self.factor <= 1:
            raise ValueError("factor must be greater than 1")
        if self.max_seconds < self.base_seconds:
            raise ValueError("max_seconds must be >= base_seconds")

    def delay_for_attempt(self, attempt: int, *, jitter: float) -> float:
        """Return the backoff delay before reconnect attempt number ``attempt`` (1-based)."""
        if attempt < 1:
            raise ValueError("attempt must be >= 1")
        if not 0.0 <= jitter < 1.0:
            raise ValueError("jitter must be in [0, 1)")
        uncapped = self.base_seconds * (self.factor ** (attempt - 1))
        capped = min(uncapped, self.max_seconds)
        return capped * jitter


__all__ = ["ReconnectPolicy"]
