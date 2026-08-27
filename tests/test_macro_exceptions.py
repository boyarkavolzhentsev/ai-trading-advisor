"""Stage 4A error taxonomy: closed hierarchy, never a legitimate market state."""

from __future__ import annotations

import pytest

from app.macro.exceptions import (
    DuplicateEventError,
    EconomicDataError,
    InvalidProviderResponseError,
    ProviderUnavailableError,
    RevisionConflictError,
    UnknownEventError,
)

SUBCLASSES = (
    ProviderUnavailableError,
    InvalidProviderResponseError,
    UnknownEventError,
    RevisionConflictError,
    DuplicateEventError,
)


@pytest.mark.parametrize("exc_cls", SUBCLASSES)
def test_every_error_subclasses_economic_data_error(exc_cls: type[Exception]) -> None:
    assert issubclass(exc_cls, EconomicDataError)


def test_economic_data_error_is_a_plain_exception() -> None:
    assert issubclass(EconomicDataError, Exception)


def test_errors_are_distinguishable_from_each_other() -> None:
    assert len(set(SUBCLASSES)) == len(SUBCLASSES)


def test_duplicate_and_conflict_are_not_the_same_class() -> None:
    assert DuplicateEventError is not RevisionConflictError
    assert not issubclass(DuplicateEventError, RevisionConflictError)
    assert not issubclass(RevisionConflictError, DuplicateEventError)


def test_errors_carry_a_message() -> None:
    error = ProviderUnavailableError("upstream timed out")
    assert "timed out" in str(error)
