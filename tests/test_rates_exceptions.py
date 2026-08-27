"""Stage 4B error taxonomy: closed hierarchy, never a legitimate market state."""

from __future__ import annotations

import pytest

from app.rates.exceptions import (
    DuplicateObservationError,
    InvalidProviderResponseError,
    ProviderUnavailableError,
    RatesDataError,
    RevisionConflictError,
    UnknownSeriesError,
)

SUBCLASSES = (
    ProviderUnavailableError,
    InvalidProviderResponseError,
    UnknownSeriesError,
    RevisionConflictError,
    DuplicateObservationError,
)


@pytest.mark.parametrize("exc_cls", SUBCLASSES)
def test_every_error_subclasses_rates_data_error(exc_cls: type[Exception]) -> None:
    assert issubclass(exc_cls, RatesDataError)


def test_rates_data_error_is_a_plain_exception() -> None:
    assert issubclass(RatesDataError, Exception)


def test_errors_are_distinguishable_from_each_other() -> None:
    assert len(set(SUBCLASSES)) == len(SUBCLASSES)


def test_duplicate_and_conflict_are_not_the_same_class() -> None:
    assert DuplicateObservationError is not RevisionConflictError
    assert not issubclass(DuplicateObservationError, RevisionConflictError)
    assert not issubclass(RevisionConflictError, DuplicateObservationError)


def test_errors_carry_a_message() -> None:
    error = ProviderUnavailableError("upstream timed out")
    assert "timed out" in str(error)


def test_no_error_silently_absorbs_into_a_legitimate_value() -> None:
    for exc_cls in (*SUBCLASSES, RatesDataError):
        assert issubclass(exc_cls, Exception)
        assert not issubclass(exc_cls, (int, float, str, bool))
