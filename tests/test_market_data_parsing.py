"""Regression tests for the generic payload-parsing helpers.

Extracted from ``app.market_data.providers.binance.mapper`` in Stage 1B so
Spot and Futures mappers can share them. ``tests/test_binance_mapper.py``
already proves the Binance-facing behaviour is unchanged; this file covers
the extracted functions directly and independently of any provider.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest
from pydantic import BaseModel

from app.market_data.exceptions import InvalidProviderResponseError, UnknownSymbolError
from app.market_data.parsing import (
    as_decimal,
    as_mapping,
    as_optional_decimal,
    as_str,
    build,
    normalize_symbol,
    optional_timestamp_from_millis,
    timestamp_from_millis,
    to_decimal,
)


class _Point(BaseModel):
    x: int
    y: int


def _millis(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)


# --------------------------------------------------------------------------- #
# normalize_symbol
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(("raw", "expected"), [("btcusdt", "BTCUSDT"), (" ethusdt ", "ETHUSDT")])
def test_normalize_symbol(raw: str, expected: str) -> None:
    assert normalize_symbol(raw) == expected


def test_normalize_symbol_rejects_blank() -> None:
    with pytest.raises(UnknownSymbolError, match="must not be empty"):
        normalize_symbol("   ")


# --------------------------------------------------------------------------- #
# as_mapping
# --------------------------------------------------------------------------- #


def test_as_mapping_accepts_dict() -> None:
    assert as_mapping({"a": 1}, "ctx") == {"a": 1}


def test_as_mapping_rejects_list() -> None:
    with pytest.raises(InvalidProviderResponseError, match="ctx payload must be an object"):
        as_mapping([], "ctx")


# --------------------------------------------------------------------------- #
# as_str
# --------------------------------------------------------------------------- #


def test_as_str_strips_and_returns() -> None:
    assert as_str({"k": " v "}, "k", "ctx") == "v"


@pytest.mark.parametrize("body", [{}, {"k": ""}, {"k": "   "}, {"k": 1}])
def test_as_str_rejects_missing_or_blank(body: dict[str, object]) -> None:
    with pytest.raises(InvalidProviderResponseError, match="no usable 'k' field"):
        as_str(body, "k", "ctx")


# --------------------------------------------------------------------------- #
# as_decimal / as_optional_decimal
# --------------------------------------------------------------------------- #


def test_as_decimal_converts_numeric_string() -> None:
    assert as_decimal({"k": "1.50"}, "k", "ctx") == Decimal("1.50")


def test_as_decimal_rejects_missing_key() -> None:
    with pytest.raises(InvalidProviderResponseError, match="ctx is missing field 'k'"):
        as_decimal({}, "k", "ctx")


def test_as_optional_decimal_returns_none_when_absent() -> None:
    assert as_optional_decimal({}, "k", "ctx") is None
    assert as_optional_decimal({"k": None}, "k", "ctx") is None


def test_as_optional_decimal_converts_present_value() -> None:
    assert as_optional_decimal({"k": "2.5"}, "k", "ctx") == Decimal("2.5")


# --------------------------------------------------------------------------- #
# to_decimal
# --------------------------------------------------------------------------- #


def test_to_decimal_accepts_numeric_string() -> None:
    assert to_decimal("12.34", "ctx") == Decimal("12.34")


def test_to_decimal_rejects_float() -> None:
    with pytest.raises(InvalidProviderResponseError, match="numeric string"):
        to_decimal(1.5, "ctx")


def test_to_decimal_rejects_bool() -> None:
    with pytest.raises(InvalidProviderResponseError, match="numeric string"):
        to_decimal(True, "ctx")


def test_to_decimal_rejects_non_numeric_string() -> None:
    with pytest.raises(InvalidProviderResponseError, match="is not a number"):
        to_decimal("n/a", "ctx")


# --------------------------------------------------------------------------- #
# timestamp_from_millis / optional_timestamp_from_millis
# --------------------------------------------------------------------------- #


def test_timestamp_from_millis_round_trips(now: datetime) -> None:
    assert timestamp_from_millis(_millis(now), "ctx") == now


def test_timestamp_from_millis_rejects_non_integer() -> None:
    with pytest.raises(InvalidProviderResponseError, match="Unix millisecond"):
        timestamp_from_millis(None, "ctx")


def test_timestamp_from_millis_rejects_bool() -> None:
    with pytest.raises(InvalidProviderResponseError, match="Unix millisecond"):
        timestamp_from_millis(True, "ctx")


def test_optional_timestamp_from_millis_none_for_none() -> None:
    assert optional_timestamp_from_millis(None, "ctx") is None


def test_optional_timestamp_from_millis_none_for_non_positive() -> None:
    assert optional_timestamp_from_millis(0, "ctx") is None
    assert optional_timestamp_from_millis(-1, "ctx") is None


def test_optional_timestamp_from_millis_parses_positive(now: datetime) -> None:
    assert optional_timestamp_from_millis(_millis(now), "ctx") == now


# --------------------------------------------------------------------------- #
# build
# --------------------------------------------------------------------------- #


def test_build_constructs_model() -> None:
    point = build(_Point, "ctx", x=1, y=2)
    assert point == _Point(x=1, y=2)


def test_build_reports_validation_error() -> None:
    with pytest.raises(InvalidProviderResponseError, match="ctx violates _Point"):
        build(_Point, "ctx", x="not-an-int", y=2)
