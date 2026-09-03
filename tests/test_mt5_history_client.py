"""Stage 10D deal-history normalization: ``MT5Client.history_deals()``
adapter behavior - BUY/SELL/NON_TRADING/UNKNOWN type mapping,
IN/OUT/INOUT/OUT_BY/UNKNOWN entry mapping, ``Decimal`` normalization, aware
UTC timestamp normalization, no raw MT5 object leakage."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.core.enums.mt5_history import MT5DealEntry, MT5DealType
from app.core.models.mt5_history import MT5Deal
from app.mt5.client import MT5Client
from app.mt5.errors import MT5NotInitializedError
from tests.mt5_history_support import WINDOW_END, WINDOW_START, default_raw_deal
from tests.mt5_support import FakeRawMT5Module, default_terminal_info

# --- deal_type mapping ---


def test_history_deals_buy_mapping() -> None:
    raw = FakeRawMT5Module(history_deals_result=(default_raw_deal(type=0, entry=0),))
    client = MT5Client(mt5_module=raw)
    client.initialize()
    status, deals = client.history_deals(start=WINDOW_START, end=WINDOW_END)
    assert status == "OK"
    assert deals[0].deal_type is MT5DealType.BUY


def test_history_deals_sell_mapping() -> None:
    raw = FakeRawMT5Module(history_deals_result=(default_raw_deal(type=1, entry=0),))
    client = MT5Client(mt5_module=raw)
    client.initialize()
    _, deals = client.history_deals(start=WINDOW_START, end=WINDOW_END)
    assert deals[0].deal_type is MT5DealType.SELL


@pytest.mark.parametrize("raw_type", [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17])
def test_history_deals_known_non_trading_mapping(raw_type: int) -> None:
    raw = FakeRawMT5Module(history_deals_result=(default_raw_deal(type=raw_type, entry=0, symbol=""),))
    client = MT5Client(mt5_module=raw)
    client.initialize()
    _, deals = client.history_deals(start=WINDOW_START, end=WINDOW_END)
    assert deals[0].deal_type is MT5DealType.NON_TRADING


def test_history_deals_unknown_raw_type_maps_to_unknown() -> None:
    raw = FakeRawMT5Module(history_deals_result=(default_raw_deal(type=999),))
    client = MT5Client(mt5_module=raw)
    client.initialize()
    _, deals = client.history_deals(start=WINDOW_START, end=WINDOW_END)
    assert deals[0].deal_type is MT5DealType.UNKNOWN


def test_history_deals_empty_symbol_normalizes_to_none() -> None:
    raw = FakeRawMT5Module(history_deals_result=(default_raw_deal(type=2, symbol="", entry=0),))
    client = MT5Client(mt5_module=raw)
    client.initialize()
    _, deals = client.history_deals(start=WINDOW_START, end=WINDOW_END)
    assert deals[0].symbol is None


# --- entry mapping ---


def test_history_deals_entry_in_mapping() -> None:
    raw = FakeRawMT5Module(history_deals_result=(default_raw_deal(entry=0),))
    client = MT5Client(mt5_module=raw)
    client.initialize()
    _, deals = client.history_deals(start=WINDOW_START, end=WINDOW_END)
    assert deals[0].entry is MT5DealEntry.IN


def test_history_deals_entry_out_mapping() -> None:
    raw = FakeRawMT5Module(history_deals_result=(default_raw_deal(entry=1),))
    client = MT5Client(mt5_module=raw)
    client.initialize()
    _, deals = client.history_deals(start=WINDOW_START, end=WINDOW_END)
    assert deals[0].entry is MT5DealEntry.OUT


def test_history_deals_entry_inout_mapping() -> None:
    raw = FakeRawMT5Module(history_deals_result=(default_raw_deal(entry=2),))
    client = MT5Client(mt5_module=raw)
    client.initialize()
    _, deals = client.history_deals(start=WINDOW_START, end=WINDOW_END)
    assert deals[0].entry is MT5DealEntry.INOUT


def test_history_deals_entry_out_by_mapping() -> None:
    raw = FakeRawMT5Module(history_deals_result=(default_raw_deal(entry=3),))
    client = MT5Client(mt5_module=raw)
    client.initialize()
    _, deals = client.history_deals(start=WINDOW_START, end=WINDOW_END)
    assert deals[0].entry is MT5DealEntry.OUT_BY


def test_history_deals_unknown_raw_entry_maps_to_unknown() -> None:
    raw = FakeRawMT5Module(history_deals_result=(default_raw_deal(entry=999),))
    client = MT5Client(mt5_module=raw)
    client.initialize()
    _, deals = client.history_deals(start=WINDOW_START, end=WINDOW_END)
    assert deals[0].entry is MT5DealEntry.UNKNOWN


# --- Decimal / timestamp normalization ---


def test_history_deals_decimal_normalization_avoids_float_repr_artifacts() -> None:
    raw = FakeRawMT5Module(
        history_deals_result=(default_raw_deal(volume=0.1, price=125.30, profit=10.10, commission=-0.7, swap=-0.3, fee=-0.05),)
    )
    client = MT5Client(mt5_module=raw)
    client.initialize()
    _, deals = client.history_deals(start=WINDOW_START, end=WINDOW_END)
    deal = deals[0]
    assert deal.volume == Decimal("0.1")
    assert deal.price == Decimal("125.3")
    assert deal.profit == Decimal("10.1")
    assert deal.commission == Decimal("-0.7")
    assert deal.swap == Decimal("-0.3")
    assert deal.fee == Decimal("-0.05")


def test_history_deals_timestamp_normalizes_to_aware_utc() -> None:
    expected = datetime(2026, 1, 1, 8, 30, 0, 500000, tzinfo=UTC)
    time_msc = int(expected.timestamp() * 1000)
    raw = FakeRawMT5Module(history_deals_result=(default_raw_deal(time_msc=time_msc),))
    client = MT5Client(mt5_module=raw)
    client.initialize()
    _, deals = client.history_deals(start=WINDOW_START, end=WINDOW_END)
    assert deals[0].time.tzinfo is not None
    assert deals[0].time == expected


def test_history_deals_fee_field_absent_falls_back_to_zero() -> None:
    """Older MT5 builds/brokers may not expose ``fee`` on the raw deal
    namedtuple at all - normalization must not raise, defaulting to 0."""
    raw_deal = default_raw_deal()
    del raw_deal.fee
    raw = FakeRawMT5Module(history_deals_result=(raw_deal,))
    client = MT5Client(mt5_module=raw)
    client.initialize()
    _, deals = client.history_deals(start=WINDOW_START, end=WINDOW_END)
    assert deals[0].fee == Decimal("0")


def test_history_deals_zero_time_msc_fails_closed() -> None:
    raw = FakeRawMT5Module(history_deals_result=(default_raw_deal(time_msc=0),))
    client = MT5Client(mt5_module=raw)
    client.initialize()
    status, deals = client.history_deals(start=WINDOW_START, end=WINDOW_END)
    assert status == "MALFORMED_TIMESTAMP"
    assert deals == ()


def test_history_deals_negative_time_msc_fails_closed() -> None:
    raw = FakeRawMT5Module(history_deals_result=(default_raw_deal(time_msc=-1000),))
    client = MT5Client(mt5_module=raw)
    client.initialize()
    status, deals = client.history_deals(start=WINDOW_START, end=WINDOW_END)
    assert status == "MALFORMED_TIMESTAMP"
    assert deals == ()


# --- read status semantics ---


def test_history_deals_no_deals_is_ok_empty() -> None:
    raw = FakeRawMT5Module(history_deals_result=())
    client = MT5Client(mt5_module=raw)
    client.initialize()
    status, deals = client.history_deals(start=WINDOW_START, end=WINDOW_END)
    assert status == "OK"
    assert deals == ()


def test_history_deals_none_result_is_unavailable() -> None:
    raw = FakeRawMT5Module(history_deals_result=None)
    client = MT5Client(mt5_module=raw)
    client.initialize()
    status, deals = client.history_deals(start=WINDOW_START, end=WINDOW_END)
    assert status == "UNAVAILABLE"
    assert deals == ()


def test_history_deals_unavailable_when_terminal_disconnected() -> None:
    raw = FakeRawMT5Module(terminal_info=default_terminal_info(connected=False))
    client = MT5Client(mt5_module=raw)
    client.initialize()
    status, deals = client.history_deals(start=WINDOW_START, end=WINDOW_END)
    assert status == "UNAVAILABLE"
    assert deals == ()


def test_history_deals_before_initialize_raises() -> None:
    raw = FakeRawMT5Module()
    client = MT5Client(mt5_module=raw)
    with pytest.raises(MT5NotInitializedError):
        client.history_deals(start=WINDOW_START, end=WINDOW_END)


def test_history_deals_after_shutdown_raises() -> None:
    raw = FakeRawMT5Module()
    client = MT5Client(mt5_module=raw)
    client.initialize()
    client.shutdown()
    with pytest.raises(MT5NotInitializedError):
        client.history_deals(start=WINDOW_START, end=WINDOW_END)


def test_history_deals_passes_start_end_through_unchanged() -> None:
    raw = FakeRawMT5Module(history_deals_result=())
    client = MT5Client(mt5_module=raw)
    client.initialize()
    client.history_deals(start=WINDOW_START, end=WINDOW_END)
    assert raw.history_deals_get_calls == [(WINDOW_START, WINDOW_END)]


def test_history_deals_raw_object_never_returned() -> None:
    raw = FakeRawMT5Module(history_deals_result=(default_raw_deal(),))
    client = MT5Client(mt5_module=raw)
    client.initialize()
    _, deals = client.history_deals(start=WINDOW_START, end=WINDOW_END)
    assert all(isinstance(deal, MT5Deal) for deal in deals)


def test_history_deals_returns_all_deals_unfiltered() -> None:
    """The client normalizes every raw deal returned - window filtering and
    trading semantics are the pure engine's job, not the client's."""
    raw = FakeRawMT5Module(
        history_deals_result=(
            default_raw_deal(ticket=1, type=0, entry=0),
            default_raw_deal(ticket=2, type=2, entry=0, symbol=""),
            default_raw_deal(ticket=3, type=999, entry=999),
        )
    )
    client = MT5Client(mt5_module=raw)
    client.initialize()
    status, deals = client.history_deals(start=WINDOW_START, end=WINDOW_END)
    assert status == "OK"
    assert {deal.ticket for deal in deals} == {1, 2, 3}
