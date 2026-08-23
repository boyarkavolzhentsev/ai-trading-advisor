"""Generic, provider-agnostic parsing of decoded JSON payloads.

Pure functions only: no HTTP, no provider-specific field names, no decisions.
Anything that does not fit the expected shape raises
``InvalidProviderResponseError`` instead of being guessed at or repaired.
Provider mappers (e.g. ``app.market_data.providers.binance.mapper``) compose
these into their own payload-specific normalization.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from app.market_data.exceptions import InvalidProviderResponseError, UnknownSymbolError

ModelT = TypeVar("ModelT", bound=BaseModel)


def normalize_symbol(symbol: str) -> str:
    """Return the upper-cased, whitespace-trimmed spelling of ``symbol``.

    Raises:
        UnknownSymbolError: if the symbol is empty.
    """
    normalized = symbol.strip().upper()
    if not normalized:
        raise UnknownSymbolError("symbol must not be empty")
    return normalized


def as_mapping(payload: Any, context: str) -> Mapping[str, Any]:
    """Assert that ``payload`` is a JSON object and return it."""
    if not isinstance(payload, Mapping):
        raise InvalidProviderResponseError(
            f"{context} payload must be an object, got {type(payload).__name__}"
        )
    return payload


def as_str(body: Mapping[str, Any], key: str, context: str) -> str:
    """Return a non-blank string field, or raise."""
    value = body.get(key)
    if not isinstance(value, str) or not value.strip():
        raise InvalidProviderResponseError(f"{context} has no usable {key!r} field")
    return value.strip()


def as_decimal(body: Mapping[str, Any], key: str, context: str) -> Decimal:
    """Return a required numeric field as an exact ``Decimal``, or raise."""
    if key not in body:
        raise InvalidProviderResponseError(f"{context} is missing field {key!r}")
    return to_decimal(body[key], f"{context} field {key!r}")


def as_optional_decimal(body: Mapping[str, Any], key: str, context: str) -> Decimal | None:
    """Return an optional numeric field as an exact ``Decimal``, or ``None``."""
    if body.get(key) is None:
        return None
    return to_decimal(body[key], f"{context} field {key!r}")


def to_decimal(value: Any, context: str) -> Decimal:
    """Convert a provider numeric string into an exact, finite ``Decimal``."""
    if isinstance(value, bool) or not isinstance(value, str | int | Decimal):
        raise InvalidProviderResponseError(
            f"{context} must be a numeric string, got {type(value).__name__}"
        )
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise InvalidProviderResponseError(f"{context} is not a number: {value!r}") from exc
    if not result.is_finite():
        raise InvalidProviderResponseError(f"{context} is not finite: {value!r}")
    return result


def timestamp_from_millis(value: Any, context: str) -> datetime:
    """Convert a Unix millisecond timestamp into a UTC-aware datetime."""
    if isinstance(value, bool) or not isinstance(value, int | str):
        raise InvalidProviderResponseError(
            f"{context} must be a Unix millisecond integer, got {type(value).__name__}"
        )
    try:
        millis = int(value)
    except ValueError as exc:
        raise InvalidProviderResponseError(f"{context} is not an integer: {value!r}") from exc
    try:
        return datetime.fromtimestamp(millis / 1000, tz=UTC)
    except (OverflowError, OSError, ValueError) as exc:
        raise InvalidProviderResponseError(f"{context} is out of range: {value!r}") from exc


def optional_timestamp_from_millis(value: Any, context: str) -> datetime | None:
    """Like ``timestamp_from_millis``, but ``None``/non-positive means unset."""
    if value is None:
        return None
    if isinstance(value, int) and not isinstance(value, bool) and value <= 0:
        return None
    return timestamp_from_millis(value, context)


def build(model: type[ModelT], context: str, **fields: Any) -> ModelT:
    """Instantiate a domain model, reporting rejection as a provider error."""
    try:
        return model(**fields)
    except ValidationError as exc:
        raise InvalidProviderResponseError(f"{context} violates {model.__name__}: {exc}") from exc


__all__ = [
    "as_decimal",
    "as_mapping",
    "as_optional_decimal",
    "as_str",
    "build",
    "normalize_symbol",
    "optional_timestamp_from_millis",
    "timestamp_from_millis",
    "to_decimal",
]
