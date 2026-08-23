"""EventRouter dispatch behaviour."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.market_data.exceptions import InvalidProviderResponseError
from app.market_data.realtime.messages import RawStreamMessage
from app.market_data.realtime.router import EventRouter

NOW = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)


def _message(stream: str, payload: object) -> RawStreamMessage:
    return RawStreamMessage(stream=stream, payload=payload, received_at=NOW)


def test_route_dispatches_by_exact_stream_name() -> None:
    router = EventRouter()
    router.register("btcusdt@aggTrade", lambda payload: {"mapped": payload})
    result = router.route(_message("btcusdt@aggTrade", {"p": "1"}))
    assert result == {"mapped": {"p": "1"}}


def test_route_dispatches_by_pattern() -> None:
    router = EventRouter()
    router.register_pattern(lambda name: name.endswith("@depth@100ms"), lambda payload: "depth")
    result = router.route(_message("ethusdt@depth@100ms", {}))
    assert result == "depth"


def test_exact_match_takes_priority_over_pattern() -> None:
    router = EventRouter()
    router.register("btcusdt@aggTrade", lambda payload: "exact")
    router.register_pattern(lambda name: name.endswith("@aggTrade"), lambda payload: "pattern")
    assert router.route(_message("btcusdt@aggTrade", {})) == "exact"


def test_unknown_stream_returns_none() -> None:
    router = EventRouter()
    result = router.route(_message("unknown@stream", {}))
    assert result is None


def test_market_data_error_from_mapper_is_isolated_as_none() -> None:
    def bad_mapper(payload: object) -> object:
        raise InvalidProviderResponseError("malformed payload")

    router = EventRouter()
    router.register("btcusdt@aggTrade", bad_mapper)
    assert router.route(_message("btcusdt@aggTrade", {})) is None


def test_non_market_data_error_propagates() -> None:
    def buggy_mapper(payload: object) -> object:
        raise AttributeError("this is a real bug, not bad provider data")

    router = EventRouter()
    router.register("btcusdt@aggTrade", buggy_mapper)
    with pytest.raises(AttributeError, match="real bug"):
        router.route(_message("btcusdt@aggTrade", {}))


def test_one_bad_stream_does_not_prevent_routing_another() -> None:
    router = EventRouter()
    router.register("bad@stream", lambda payload: (_ for _ in ()).throw(InvalidProviderResponseError("x")))
    router.register("good@stream", lambda payload: "ok")

    assert router.route(_message("bad@stream", {})) is None
    assert router.route(_message("good@stream", {})) == "ok"
