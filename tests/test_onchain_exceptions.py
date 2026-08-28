"""Stage 4E error hierarchy shape."""

from __future__ import annotations

from app.onchain.exceptions import (
    DuplicateOnChainObservationError,
    InvalidProviderResponseError,
    OnChainDataError,
    ProviderUnavailableError,
    UnknownOnChainObservationError,
)


def test_all_onchain_errors_derive_from_onchain_data_error() -> None:
    for exc_cls in (
        ProviderUnavailableError,
        InvalidProviderResponseError,
        UnknownOnChainObservationError,
        DuplicateOnChainObservationError,
    ):
        assert issubclass(exc_cls, OnChainDataError)


def test_onchain_data_error_derives_from_exception() -> None:
    assert issubclass(OnChainDataError, Exception)


def test_no_revision_conflict_error_exists() -> None:
    import app.onchain.exceptions as exceptions_module

    assert not hasattr(exceptions_module, "RevisionConflictError")


def test_exceptions_are_distinct_classes() -> None:
    classes = {
        ProviderUnavailableError,
        InvalidProviderResponseError,
        UnknownOnChainObservationError,
        DuplicateOnChainObservationError,
    }
    assert len(classes) == 4


def test_no_per_family_exception_classes_exist() -> None:
    """One shared hierarchy across all four metric families - no
    NetworkActivity/Supply/ExchangeFlow/Stablecoin-specific exception
    subclass exists."""
    import app.onchain.exceptions as exceptions_module

    forbidden_names = (
        "NetworkActivityError",
        "SupplyError",
        "ExchangeFlowError",
        "StablecoinSupplyError",
        "DuplicateNetworkActivityError",
        "DuplicateSupplyError",
        "DuplicateExchangeFlowError",
        "DuplicateStablecoinSupplyError",
    )
    for name in forbidden_names:
        assert not hasattr(exceptions_module, name)
