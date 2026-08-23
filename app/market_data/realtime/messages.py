"""Transport-to-router boundary message.

Carries an opaque, still provider-shaped payload plus enough context for the
router to pick a mapper - the transport never understands what is inside it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class RawStreamMessage:
    """One decoded-but-unmapped event received from a WebSocket transport."""

    stream: str
    payload: Any
    received_at: datetime


__all__ = ["RawStreamMessage"]
