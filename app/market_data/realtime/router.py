"""Raw event routing: dispatches ``RawStreamMessage`` to provider mappers.

Provider-agnostic: it only knows a stream-name -> mapper table, supplied by
the caller. Never parses provider JSON itself - that stays inside the
mapper functions it dispatches to.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from app.market_data.exceptions import MarketDataError
from app.market_data.realtime.messages import RawStreamMessage

logger = logging.getLogger(__name__)

MapperFn = Callable[[Any], Any]


class EventRouter:
    """Dispatches raw messages to a mapper selected by stream-name pattern.

    Exact stream names are checked first, then registered predicates in
    registration order. A stream with no matching mapper, or provider data a
    mapper rejects as unusable (``MarketDataError``), both result in
    ``route`` returning ``None`` - logged, not raised. Any other exception
    raised by a mapper is a programming error and is deliberately **not**
    caught here: it propagates to the caller.
    """

    def __init__(self) -> None:
        self._exact: dict[str, MapperFn] = {}
        self._predicated: list[tuple[Callable[[str], bool], MapperFn]] = []

    def register(self, stream_name: str, mapper: MapperFn) -> None:
        """Register a mapper for one exact stream name."""
        self._exact[stream_name] = mapper

    def register_pattern(self, predicate: Callable[[str], bool], mapper: MapperFn) -> None:
        """Register a mapper for every stream name matching ``predicate``."""
        self._predicated.append((predicate, mapper))

    def route(self, message: RawStreamMessage) -> Any | None:
        """Map ``message`` to a domain event, or ``None`` if it was dropped."""
        mapper = self._select(message.stream)
        if mapper is None:
            logger.warning("no mapper registered for stream %r", message.stream)
            return None
        try:
            return mapper(message.payload)
        except MarketDataError as exc:
            logger.warning("dropping unusable payload on stream %r: %s", message.stream, exc)
            return None

    def _select(self, stream_name: str) -> MapperFn | None:
        if stream_name in self._exact:
            return self._exact[stream_name]
        for predicate, mapper in self._predicated:
            if predicate(stream_name):
                return mapper
        return None


__all__ = ["EventRouter"]
