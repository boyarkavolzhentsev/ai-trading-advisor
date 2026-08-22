"""Low-level Binance Spot public REST client.

Sole responsibility: perform HTTP GETs and turn every transport-level or
protocol-level failure into a project exception. It does no normalization and
knows nothing about domain models.

Public market data endpoints only: no API key, no signing, no private
endpoints.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from http import HTTPStatus
from types import TracebackType
from typing import Any, Self

import httpx

from app.market_data.exceptions import (
    InvalidProviderResponseError,
    ProviderUnavailableError,
    UnknownSymbolError,
)
from app.market_data.providers.binance.constants import (
    BINANCE_SPOT_BASE_URL,
    DEFAULT_TIMEOUT_SECONDS,
    RATE_LIMIT_STATUS_CODES,
    UNKNOWN_SYMBOL_CODES,
)

logger = logging.getLogger(__name__)

QueryParams = Mapping[str, str | int]


class BinanceRestClient:
    """Thin synchronous HTTP wrapper around the Binance Spot REST API."""

    def __init__(
        self,
        *,
        base_url: str = BINANCE_SPOT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        http_client: httpx.Client | None = None,
    ) -> None:
        """Create a client.

        Args:
            base_url: REST base URL, overridable for testnet or a mirror.
            timeout: total per-request timeout in seconds.
            http_client: pre-configured ``httpx.Client``; when given, the
                caller owns its lifecycle and ``base_url``/``timeout`` are
                assumed to be set on it already. Used by tests to inject a
                mock transport.
        """
        self._base_url = base_url
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(base_url=base_url, timeout=timeout)

    @property
    def base_url(self) -> str:
        """Configured REST base URL."""
        return self._base_url

    def get(self, path: str, params: QueryParams | None = None) -> Any:
        """GET ``path`` and return the decoded JSON payload.

        Raises:
            ProviderUnavailableError: transport failure, timeout, rate limit or
                server-side error.
            UnknownSymbolError: Binance reports the symbol as invalid.
            InvalidProviderResponseError: any other rejected request, or a body
                that is not valid JSON.
        """
        try:
            response = self._client.get(path, params=dict(params or {}))
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(
                f"binance request to {path} failed: {type(exc).__name__}: {exc}"
            ) from exc

        if response.status_code != HTTPStatus.OK:
            self._raise_for_status(response, path)

        try:
            return response.json()
        except ValueError as exc:
            raise InvalidProviderResponseError(
                f"binance response for {path} is not valid JSON"
            ) from exc

    def close(self) -> None:
        """Close the underlying HTTP client if this instance created it."""
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def _raise_for_status(self, response: httpx.Response, path: str) -> None:
        """Translate a non-200 response into a project exception."""
        status = response.status_code
        code, message = self._error_payload(response)
        detail = f"binance {path} returned HTTP {status}"
        if code is not None:
            detail = f"{detail} (code {code}: {message})"

        logger.debug("binance error response: %s", detail)

        if code is not None and code in UNKNOWN_SYMBOL_CODES:
            raise UnknownSymbolError(detail)
        if status in RATE_LIMIT_STATUS_CODES or status >= HTTPStatus.INTERNAL_SERVER_ERROR:
            raise ProviderUnavailableError(detail)
        raise InvalidProviderResponseError(detail)

    @staticmethod
    def _error_payload(response: httpx.Response) -> tuple[int | None, str]:
        """Extract Binance's ``{"code": ..., "msg": ...}`` error body, if any."""
        try:
            payload = response.json()
        except ValueError:
            return None, response.text[:200]
        if not isinstance(payload, dict):
            return None, str(payload)[:200]
        code = payload.get("code")
        message = str(payload.get("msg", ""))
        return (code if isinstance(code, int) else None), message


__all__ = ["BinanceRestClient"]
