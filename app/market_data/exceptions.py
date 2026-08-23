"""Project-specific market data errors.

Every failure that crosses the provider boundary is one of these. HTTP client
exceptions (``httpx``) and provider error payloads are translated inside the
provider layer and never reach callers.
"""

from __future__ import annotations


class MarketDataError(Exception):
    """Base class for every market data failure."""


class ProviderUnavailableError(MarketDataError):
    """Provider could not be reached or failed transiently.

    Network errors, timeouts, rate limiting and 5xx responses.
    """


class InvalidProviderResponseError(MarketDataError):
    """Provider answered, but the payload does not satisfy the contract.

    Missing fields, non-numeric values, unusable series (empty, duplicated or
    unordered candles) and mismatched symbols.
    """


class UnsupportedTimeframeError(MarketDataError):
    """Requested timeframe has no mapping for the selected provider."""


class UnknownSymbolError(MarketDataError):
    """Provider does not know the requested symbol."""


class DataNotAvailableError(MarketDataError):
    """The requested data does not exist on this transport for this provider.

    Distinct from ``ProviderUnavailableError``: this is not a transient
    failure that a retry could fix. It means the capability is not offered by
    this adapter at all (e.g. Binance liquidations are REST-unavailable and
    require the WebSocket transport added in a later stage).
    """


__all__ = [
    "DataNotAvailableError",
    "InvalidProviderResponseError",
    "MarketDataError",
    "ProviderUnavailableError",
    "UnknownSymbolError",
    "UnsupportedTimeframeError",
]
