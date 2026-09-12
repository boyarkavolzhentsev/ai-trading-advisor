"""``app.market_data.providers.mt5.timezone.normalize_mt5_server_timestamp``
- MT5's raw ``time`` interpreted as broker-local wall-clock digits, then
resolved via the shared DST-safe primitive. Reuses the same proven
Europe/Bucharest 2026-03-29/2026-10-25 transition dates as
``tests/test_time_normalization.py``/``tests/test_high_impact_event_file_
reader.py`` for consistency."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.market_data.providers.mt5.timezone import normalize_mt5_server_timestamp


def _raw_epoch_for_wall_clock_digits(naive_local: datetime) -> int:
    """The raw MT5 ``time`` value that encodes ``naive_local``'s digits -
    the exact inverse of ``normalize_mt5_server_timestamp``'s first step."""
    return int(naive_local.replace(tzinfo=UTC).timestamp())


def test_known_broker_wall_clock_digits_convert_to_expected_utc() -> None:
    raw_epoch = _raw_epoch_for_wall_clock_digits(datetime(2026, 1, 1, 15, 0, 0))
    result = normalize_mt5_server_timestamp(raw_epoch, "Europe/Bucharest")
    assert result == datetime(2026, 1, 1, 13, 0, 0, tzinfo=UTC)  # winter, UTC+2


@pytest.mark.parametrize(
    ("server_timezone", "expected_offset_hours"),
    [
        ("Europe/Bucharest", 2),
        ("America/New_York", -5),
        ("Asia/Tokyo", 9),
    ],
)
def test_multiple_iana_zones_convert_parametrically_not_hardcoded(
    server_timezone: str, expected_offset_hours: int
) -> None:
    """Three unrelated zones, three different offsets, one function - proves
    the conversion is driven entirely by ``server_timezone``, never a
    hardcoded UTC+3."""
    naive_local = datetime(2026, 1, 15, 12, 0, 0)  # clear of any DST edge in all three zones
    raw_epoch = _raw_epoch_for_wall_clock_digits(naive_local)
    result = normalize_mt5_server_timestamp(raw_epoch, server_timezone)
    expected = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC) - timedelta(hours=expected_offset_hours)
    assert result == expected


def test_dst_spring_forward_nonexistent_broker_time_raises() -> None:
    raw_epoch = _raw_epoch_for_wall_clock_digits(datetime(2026, 3, 29, 3, 30, 0))
    with pytest.raises(ValueError, match="does not exist"):
        normalize_mt5_server_timestamp(raw_epoch, "Europe/Bucharest")


def test_dst_fall_back_ambiguous_broker_time_raises() -> None:
    raw_epoch = _raw_epoch_for_wall_clock_digits(datetime(2026, 10, 25, 3, 30, 0))
    with pytest.raises(ValueError, match="ambiguous"):
        normalize_mt5_server_timestamp(raw_epoch, "Europe/Bucharest")
