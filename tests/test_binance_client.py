"""BinanceRestClient transport and error translation.

Every request is served by an in-process mock transport: no test in this suite
touches the network.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from app.market_data.exceptions import (
    InvalidProviderResponseError,
    ProviderUnavailableError,
    UnknownSymbolError,
)
from app.market_data.providers.binance.client import BinanceRestClient
from app.market_data.providers.binance.constants import (
    BINANCE_SPOT_BASE_URL,
    TICKER_PRICE_PATH,
)

Handler = Callable[[httpx.Request], httpx.Response]


def _client(handler: Handler) -> BinanceRestClient:
    transport = httpx.MockTransport(handler)
    return BinanceRestClient(
        http_client=httpx.Client(base_url=BINANCE_SPOT_BASE_URL, transport=transport)
    )


def _responder(status: int, payload: object) -> Handler:
    return lambda _request: httpx.Response(status, json=payload)


def test_successful_get_returns_decoded_payload() -> None:
    client = _client(_responder(200, {"symbol": "BTCUSDT", "price": "1"}))
    assert client.get(TICKER_PRICE_PATH) == {"symbol": "BTCUSDT", "price": "1"}


def test_query_parameters_are_sent() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.url.params))
        return httpx.Response(200, json=[])

    _client(handler).get("/api/v3/klines", {"symbol": "BTCUSDT", "interval": "5m", "limit": 5})
    assert seen == {"symbol": "BTCUSDT", "interval": "5m", "limit": "5"}


def test_request_targets_configured_base_url() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json={})

    client = BinanceRestClient(
        http_client=httpx.Client(
            base_url="https://data-api.binance.vision", transport=httpx.MockTransport(handler)
        )
    )
    client.get(TICKER_PRICE_PATH)
    assert seen == [f"https://data-api.binance.vision{TICKER_PRICE_PATH}"]


def test_base_url_is_exposed() -> None:
    assert BinanceRestClient(base_url="https://example.test").base_url == "https://example.test"


def test_network_error_becomes_provider_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(ProviderUnavailableError, match="ConnectError"):
        _client(handler).get(TICKER_PRICE_PATH)


def test_timeout_becomes_provider_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    with pytest.raises(ProviderUnavailableError, match="ReadTimeout"):
        _client(handler).get(TICKER_PRICE_PATH)


def test_invalid_symbol_code_becomes_unknown_symbol() -> None:
    client = _client(_responder(400, {"code": -1121, "msg": "Invalid symbol."}))
    with pytest.raises(UnknownSymbolError, match="code -1121"):
        client.get(TICKER_PRICE_PATH, {"symbol": "NOPEUSDT"})


@pytest.mark.parametrize("status", [429, 418, 500, 503])
def test_rate_limit_and_server_errors_become_provider_unavailable(status: int) -> None:
    client = _client(_responder(status, {"code": -1003, "msg": "Too many requests."}))
    with pytest.raises(ProviderUnavailableError, match=f"HTTP {status}"):
        client.get(TICKER_PRICE_PATH)


def test_other_client_error_becomes_invalid_response() -> None:
    client = _client(_responder(400, {"code": -1104, "msg": "Not all sent parameters were read."}))
    with pytest.raises(InvalidProviderResponseError, match="HTTP 400"):
        client.get(TICKER_PRICE_PATH)


def test_non_json_error_body_is_reported() -> None:
    client = _client(lambda _request: httpx.Response(404, text="<html>not found</html>"))
    with pytest.raises(InvalidProviderResponseError, match="HTTP 404"):
        client.get(TICKER_PRICE_PATH)


def test_non_json_success_body_becomes_invalid_response() -> None:
    client = _client(lambda _request: httpx.Response(200, text="not json"))
    with pytest.raises(InvalidProviderResponseError, match="not valid JSON"):
        client.get(TICKER_PRICE_PATH)


def test_httpx_exceptions_never_escape() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ProtocolError("bad chunk", request=request)

    with pytest.raises(ProviderUnavailableError) as failure:
        _client(handler).get(TICKER_PRICE_PATH)
    assert isinstance(failure.value.__cause__, httpx.HTTPError)


def test_injected_client_is_not_closed_by_close() -> None:
    http_client = httpx.Client(transport=httpx.MockTransport(_responder(200, {})))
    BinanceRestClient(http_client=http_client).close()
    assert not http_client.is_closed


def test_owned_client_is_closed_on_context_exit() -> None:
    with BinanceRestClient() as client:
        pass
    assert client._client.is_closed  # noqa: SLF001 - lifecycle assertion
