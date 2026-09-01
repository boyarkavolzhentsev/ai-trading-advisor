"""Stage 10A ``MT5Client`` lifecycle: construction performs no I/O,
``initialize()`` is the only I/O-performing call, initialized-only methods
raise ``MT5NotInitializedError`` before init/after shutdown, ``shutdown()``
is idempotent, no reconnect/polling occurs, and no raw MT5 object/tuple ever
escapes the adapter."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.enums.mt5_runtime import MT5ConnectivityState
from app.core.models.mt5_runtime import MT5AccountFacts, MT5RuntimeStatus
from app.mt5.client import MT5Client
from app.mt5.errors import MT5NotInitializedError
from tests.mt5_support import FakeRawMT5Module, default_account_info


def test_construction_performs_no_io() -> None:
    raw = FakeRawMT5Module()
    MT5Client(mt5_module=raw)
    assert raw.initialize_calls == []
    assert raw.shutdown_calls == 0


def test_initialize_performs_io_exactly_once() -> None:
    raw = FakeRawMT5Module()
    client = MT5Client(mt5_module=raw)
    client.initialize()
    assert len(raw.initialize_calls) == 1


def test_account_facts_before_initialize_raises() -> None:
    raw = FakeRawMT5Module()
    client = MT5Client(mt5_module=raw)
    with pytest.raises(MT5NotInitializedError):
        client.account_facts()


def test_runtime_status_before_initialize_raises() -> None:
    raw = FakeRawMT5Module()
    client = MT5Client(mt5_module=raw)
    with pytest.raises(MT5NotInitializedError):
        client.runtime_status()


def test_account_facts_after_shutdown_raises() -> None:
    raw = FakeRawMT5Module()
    client = MT5Client(mt5_module=raw)
    client.initialize()
    client.shutdown()
    with pytest.raises(MT5NotInitializedError):
        client.account_facts()


def test_runtime_status_after_shutdown_raises() -> None:
    raw = FakeRawMT5Module()
    client = MT5Client(mt5_module=raw)
    client.initialize()
    client.shutdown()
    with pytest.raises(MT5NotInitializedError):
        client.runtime_status()


def test_shutdown_idempotent() -> None:
    raw = FakeRawMT5Module()
    client = MT5Client(mt5_module=raw)
    client.initialize()
    client.shutdown()
    client.shutdown()
    client.shutdown()
    assert raw.shutdown_calls == 3  # each call reaches the underlying module safely, no exception


def test_shutdown_before_initialize_does_not_call_underlying_module() -> None:
    raw = FakeRawMT5Module()
    client = MT5Client(mt5_module=raw)
    client.shutdown()
    assert raw.shutdown_calls == 0


def test_reinitialize_after_shutdown_works() -> None:
    raw = FakeRawMT5Module()
    client = MT5Client(mt5_module=raw)
    client.initialize()
    client.shutdown()
    status = client.initialize()
    assert status.state is MT5ConnectivityState.AVAILABLE
    assert client.account_facts() is not None


def test_no_reconnect_or_polling_on_repeated_status_calls() -> None:
    raw = FakeRawMT5Module()
    client = MT5Client(mt5_module=raw)
    client.initialize()
    client.runtime_status()
    client.runtime_status()
    client.runtime_status()
    assert len(raw.initialize_calls) == 1  # runtime_status never re-initializes


def test_repeated_identical_raw_input_produces_identical_normalized_facts() -> None:
    raw = FakeRawMT5Module(account_info=default_account_info(equity=77777.0))
    client = MT5Client(mt5_module=raw)
    client.initialize()
    first = client.account_facts()
    second = client.account_facts()
    assert first is not None and second is not None
    assert first.model_dump(exclude={"as_of"}) == second.model_dump(exclude={"as_of"})


def test_raw_mt5_object_never_returned_from_initialize() -> None:
    raw = FakeRawMT5Module()
    client = MT5Client(mt5_module=raw)
    status = client.initialize()
    assert isinstance(status, MT5RuntimeStatus)
    assert not isinstance(status, FakeRawMT5Module)


def test_raw_mt5_object_never_returned_from_account_facts() -> None:
    raw = FakeRawMT5Module()
    client = MT5Client(mt5_module=raw)
    client.initialize()
    facts = client.account_facts()
    assert isinstance(facts, MT5AccountFacts)


def test_raw_last_error_tuple_never_returned() -> None:
    raw = FakeRawMT5Module(initialize_result=False, last_error=(5, "some raw broker string"))
    client = MT5Client(mt5_module=raw)
    status = client.initialize()
    assert isinstance(status.reason, str) or status.reason is None
    assert not isinstance(status.reason, tuple)


def test_margin_level_decimal_conversion_avoids_float_repr_artifacts() -> None:
    raw = FakeRawMT5Module(account_info=default_account_info(margin_level=125.30))
    client = MT5Client(mt5_module=raw)
    client.initialize()
    facts = client.account_facts()
    assert facts is not None
    assert facts.margin_level == Decimal("125.3")
