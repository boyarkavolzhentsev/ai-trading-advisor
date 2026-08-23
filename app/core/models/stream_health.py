"""Real-time stream health/freshness verdict contract.

Immutable snapshot produced on demand by a stream's internal health tracker -
mirrors ``DataQuality``'s "verdict object built when asked" pattern rather
than being a continuously mutated record itself.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from app.core.enums.stream import StreamStatus
from app.core.models.base import DomainModel, Symbol, Timestamp


class StreamHealth(DomainModel):
    """Point-in-time health verdict of one real-time stream."""

    provider: str = Field(min_length=1)
    stream: str = Field(min_length=1)
    symbol: Symbol | None = None
    status: StreamStatus
    last_message_at: Timestamp | None = None
    last_error: str | None = None
    reconnect_count: Annotated[int, Field(ge=0)] = 0
    dropped_message_count: Annotated[int, Field(ge=0)] = 0
    checked_at: Timestamp
