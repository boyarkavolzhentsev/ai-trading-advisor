"""Stage 10B ``compute_trading_day_key`` pure calculation: timezone-aware-
only, DST-safe, no wall-clock reads, deterministic across multiple zones and
non-zero rollover hours.

Also covers Stage 10D's ``trading_day_interval`` - the canonical inverse/
boundary companion to ``compute_trading_day_key`` added to this same
module."""

from __future__ import annotations

import ast
import inspect
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

import app.mt5.rollover as rollover_module
from app.core.config.mt5_rollover import MT5RolloverPolicyConfig
from app.mt5.rollover import compute_trading_day_key, trading_day_interval

_UTC_MIDNIGHT = MT5RolloverPolicyConfig(rollover_timezone="UTC", rollover_hour=0)


def test_naive_timestamp_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        compute_trading_day_key(datetime(2026, 1, 1, 12, 0, 0), _UTC_MIDNIGHT)


def test_aware_timestamp_accepted() -> None:
    as_of = datetime(2026, 1, 1, 12, 0, 0, tzinfo=ZoneInfo("UTC"))
    assert compute_trading_day_key(as_of, _UTC_MIDNIGHT) == "2026-01-01"


def test_utc_midnight_boundary() -> None:
    just_before = datetime(2026, 6, 15, 23, 59, 59, tzinfo=ZoneInfo("UTC"))
    just_after = datetime(2026, 6, 16, 0, 0, 0, tzinfo=ZoneInfo("UTC"))
    assert compute_trading_day_key(just_before, _UTC_MIDNIGHT) == "2026-06-15"
    assert compute_trading_day_key(just_after, _UTC_MIDNIGHT) == "2026-06-16"


def test_non_zero_rollover_hour_shifts_boundary() -> None:
    policy = MT5RolloverPolicyConfig(rollover_timezone="UTC", rollover_hour=5)
    just_before = datetime(2026, 6, 15, 4, 59, 59, tzinfo=ZoneInfo("UTC"))
    just_after = datetime(2026, 6, 15, 5, 0, 0, tzinfo=ZoneInfo("UTC"))
    assert compute_trading_day_key(just_before, policy) == "2026-06-14"
    assert compute_trading_day_key(just_after, policy) == "2026-06-15"


def test_same_instant_different_timezones_can_yield_different_keys() -> None:
    as_of = datetime(2026, 6, 15, 23, 0, 0, tzinfo=ZoneInfo("UTC"))
    utc_key = compute_trading_day_key(as_of, MT5RolloverPolicyConfig(rollover_timezone="UTC", rollover_hour=0))
    tokyo_key = compute_trading_day_key(as_of, MT5RolloverPolicyConfig(rollover_timezone="Asia/Tokyo", rollover_hour=0))
    assert utc_key == "2026-06-15"
    assert tokyo_key == "2026-06-16"  # Asia/Tokyo is UTC+9, already past local midnight


def test_input_in_non_broker_timezone_is_converted_before_keying() -> None:
    """``as_of`` may be aware in any timezone - conversion to
    ``rollover_timezone`` happens inside ``compute_trading_day_key``."""
    as_of_ny = datetime(2026, 6, 15, 21, 30, 0, tzinfo=ZoneInfo("America/New_York"))  # 01:30 UTC next day
    key = compute_trading_day_key(as_of_ny, _UTC_MIDNIGHT)
    assert key == "2026-06-16"


def test_dst_spring_forward_same_calendar_day_before_and_after_transition() -> None:
    """Europe/Bucharest springs forward on 2026-03-29 at 03:00 local (jumps
    to 04:00). Times before and after the jump, still within the same local
    calendar day, must key identically."""
    tz = ZoneInfo("Europe/Bucharest")
    before_transition = datetime(2026, 3, 29, 0, 30, 0, tzinfo=tz)
    after_transition = datetime(2026, 3, 29, 5, 0, 0, tzinfo=tz)
    policy = MT5RolloverPolicyConfig(rollover_timezone="Europe/Bucharest", rollover_hour=0)
    assert compute_trading_day_key(before_transition, policy) == "2026-03-29"
    assert compute_trading_day_key(after_transition, policy) == "2026-03-29"


def test_dst_transition_advances_key_by_exactly_one_day() -> None:
    """Two instants 24h apart in UTC, straddling the spring-forward
    transition, must still advance the broker-local trading day by exactly
    one calendar day - not zero, not two."""
    policy = MT5RolloverPolicyConfig(rollover_timezone="Europe/Bucharest", rollover_hour=0)
    before = datetime(2026, 3, 28, 22, 0, 0, tzinfo=ZoneInfo("UTC"))
    after = datetime(2026, 3, 29, 22, 0, 0, tzinfo=ZoneInfo("UTC"))
    key_before = compute_trading_day_key(before, policy)
    key_after = compute_trading_day_key(after, policy)
    assert (datetime.fromisoformat(key_after) - datetime.fromisoformat(key_before)).days == 1


# --- trading_day_interval (Stage 10D) ---


def test_interval_start_included_via_compute_trading_day_key_roundtrip() -> None:
    start, _ = trading_day_interval("2026-06-15", _UTC_MIDNIGHT)
    assert compute_trading_day_key(start, _UTC_MIDNIGHT) == "2026-06-15"


def test_interval_end_excluded_via_compute_trading_day_key_roundtrip() -> None:
    _, end = trading_day_interval("2026-06-15", _UTC_MIDNIGHT)
    assert compute_trading_day_key(end, _UTC_MIDNIGHT) == "2026-06-16"


def test_interval_instant_before_start_belongs_to_previous_day() -> None:
    start, _ = trading_day_interval("2026-06-15", _UTC_MIDNIGHT)
    just_before = start - timedelta(microseconds=1)
    assert compute_trading_day_key(just_before, _UTC_MIDNIGHT) == "2026-06-14"


def test_interval_instant_before_end_belongs_to_this_day() -> None:
    _, end = trading_day_interval("2026-06-15", _UTC_MIDNIGHT)
    just_before = end - timedelta(microseconds=1)
    assert compute_trading_day_key(just_before, _UTC_MIDNIGHT) == "2026-06-15"


def test_interval_is_exactly_one_day_wide_under_utc() -> None:
    start, end = trading_day_interval("2026-06-15", _UTC_MIDNIGHT)
    assert end - start == timedelta(days=1)


def test_interval_start_hour_matches_rollover_hour() -> None:
    policy = MT5RolloverPolicyConfig(rollover_timezone="UTC", rollover_hour=5)
    start, end = trading_day_interval("2026-06-15", policy)
    assert start == datetime(2026, 6, 15, 5, 0, 0, tzinfo=ZoneInfo("UTC"))
    assert end == datetime(2026, 6, 16, 5, 0, 0, tzinfo=ZoneInfo("UTC"))
    assert compute_trading_day_key(start, policy) == "2026-06-15"
    assert compute_trading_day_key(end, policy) == "2026-06-16"


def test_interval_non_utc_timezone_roundtrips() -> None:
    policy = MT5RolloverPolicyConfig(rollover_timezone="Asia/Tokyo", rollover_hour=0)
    start, end = trading_day_interval("2026-06-15", policy)
    assert compute_trading_day_key(start, policy) == "2026-06-15"
    assert compute_trading_day_key(end, policy) == "2026-06-16"
    assert compute_trading_day_key(end - timedelta(microseconds=1), policy) == "2026-06-15"


def test_interval_dst_spring_forward_still_roundtrips() -> None:
    """Europe/Bucharest springs forward on 2026-03-29 - the interval for
    the day before the transition must still key back correctly at both
    boundaries even though ``end`` lands on the transition day."""
    policy = MT5RolloverPolicyConfig(rollover_timezone="Europe/Bucharest", rollover_hour=0)
    start, end = trading_day_interval("2026-03-28", policy)
    assert compute_trading_day_key(start, policy) == "2026-03-28"
    assert compute_trading_day_key(end, policy) == "2026-03-29"
    assert compute_trading_day_key(end - timedelta(microseconds=1), policy) == "2026-03-28"


def test_interval_dst_transition_day_itself_roundtrips() -> None:
    """The trading day whose boundary companion ``end`` falls exactly on
    the spring-forward transition day must still round-trip correctly."""
    policy = MT5RolloverPolicyConfig(rollover_timezone="Europe/Bucharest", rollover_hour=0)
    start, end = trading_day_interval("2026-03-29", policy)
    assert compute_trading_day_key(start, policy) == "2026-03-29"
    assert compute_trading_day_key(end, policy) == "2026-03-30"


def test_interval_naive_wall_clock_arithmetic_not_used_across_dst() -> None:
    """A naive ``+24h`` shortcut would land at the wrong wall-clock hour
    across a DST transition; the zoneinfo-aware ``timedelta(days=1)``
    approach must not."""
    policy = MT5RolloverPolicyConfig(rollover_timezone="Europe/Bucharest", rollover_hour=0)
    start, end = trading_day_interval("2026-03-28", policy)
    assert start.hour == 0
    assert end.hour == 0


def _rollover_module_imports() -> set[str]:
    tree = ast.parse(inspect.getsource(rollover_module))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_compute_trading_day_key_source_never_calls_wall_clock() -> None:
    """AST-based (not substring) so this cannot false-positive on the
    module's own explanatory docstrings mentioning ``datetime.now(UTC)`` in
    prose."""
    tree = ast.parse(inspect.getsource(rollover_module))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in {"now", "utcnow"}, "pure rollover module must not read the wall clock"


def test_rollover_module_never_imports_metatrader5() -> None:
    offending = {name for name in _rollover_module_imports() if name == "MetaTrader5" or name.startswith("MetaTrader5.")}
    assert not offending


def test_rollover_module_never_imports_filesystem_modules() -> None:
    assert _rollover_module_imports().isdisjoint({"pathlib", "os", "app.mt5.persistence"})
