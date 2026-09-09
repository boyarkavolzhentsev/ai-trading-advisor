"""MQL5 calendar bridge file-reader tests (Corrective V1 Integration, test
groups AA/AB/AC + AD determinism, no-write/no-MT5 hygiene; plus the
timezone design closure's server-local -> UTC conversion tests)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.core.config.high_impact_event_bridge import HighImpactEventCalendarTimezoneConfig
from app.core.enums.high_impact_event import HighImpactEventDataQuality
from app.high_impact_event_bridge.file_reader import read_high_impact_event_context

AS_OF = datetime(2026, 1, 2, 14, 30, 0, tzinfo=UTC)
STALENESS_THRESHOLD = timedelta(hours=1)
UTC_TZ_CONFIG = HighImpactEventCalendarTimezoneConfig(server_timezone="UTC")

_VALID_PAYLOAD = {
    "schema_version": 2,
    "producer": "mt5_calendar_bridge",
    "generated_at": "2026-01-02T14:00:00Z",
    "events": [
        {
            "provider_event_id": "1:2026-01-02",
            "event_time_server": "2026-01-02T14:30:00",
            "observed_offset_seconds": 0,
            "importance": "HIGH",
            "scope": ["USD"],
            "event_code": "US_NFP",
            "name": "Non-Farm Payrolls",
        }
    ],
}


def _write(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _read(path: Path, *, timezone_config: HighImpactEventCalendarTimezoneConfig | None = UTC_TZ_CONFIG):
    return read_high_impact_event_context(
        path, as_of=AS_OF, staleness_threshold=STALENESS_THRESHOLD, timezone_config=timezone_config
    )


def test_missing_file_is_unavailable(tmp_path: Path) -> None:
    result = _read(tmp_path / "absent.json")
    assert result.data_quality is HighImpactEventDataQuality.UNAVAILABLE
    assert result.events == ()
    assert result.generated_at is None


def test_fresh_valid_file_parses_correctly(tmp_path: Path) -> None:
    path = tmp_path / "calendar.json"
    _write(path, _VALID_PAYLOAD)

    result = _read(path)

    assert result.data_quality is HighImpactEventDataQuality.FRESH
    assert result.producer == "mt5_calendar_bridge"
    assert result.generated_at == datetime(2026, 1, 2, 14, 0, 0, tzinfo=UTC)
    assert len(result.events) == 1
    event = result.events[0]
    assert event.provider_event_id == "1:2026-01-02"
    assert event.event_code == "US_NFP"
    assert event.importance.value == "HIGH"
    assert event.scope == ("USD",)
    assert event.event_time == datetime(2026, 1, 2, 14, 30, 0, tzinfo=UTC)


def test_stale_generated_at_fails_open_with_no_events(tmp_path: Path) -> None:
    path = tmp_path / "calendar.json"
    payload = dict(_VALID_PAYLOAD, generated_at="2026-01-02T12:00:00Z")  # 2h30m before AS_OF, threshold is 1h
    _write(path, payload)

    result = _read(path)

    assert result.data_quality is HighImpactEventDataQuality.STALE
    assert result.events == ()
    assert result.generated_at == datetime(2026, 1, 2, 12, 0, 0, tzinfo=UTC)


def test_malformed_json_is_malformed(tmp_path: Path) -> None:
    path = tmp_path / "calendar.json"
    path.write_text("{not valid json", encoding="utf-8")

    result = _read(path)

    assert result.data_quality is HighImpactEventDataQuality.MALFORMED
    assert result.events == ()
    assert result.generated_at is None


def test_wrong_schema_version_is_malformed(tmp_path: Path) -> None:
    path = tmp_path / "calendar.json"
    _write(path, dict(_VALID_PAYLOAD, schema_version=3))

    result = _read(path)

    assert result.data_quality is HighImpactEventDataQuality.MALFORMED


def test_retired_schema_version_1_is_explicitly_rejected_not_guessed(tmp_path: Path) -> None:
    """The old (pre-timezone-closure) ``schema_version: 1`` shape carried an
    already-aware ``event_time`` field - genuinely incompatible with the
    current ``event_time_server``/``observed_offset_seconds`` shape. A
    version-1-labelled payload must be rejected outright, never accepted
    via any dual-shape/compatibility-guessing path."""
    path = tmp_path / "calendar.json"
    legacy_shape_payload = {
        "schema_version": 1,
        "producer": "mt5_calendar_bridge",
        "generated_at": "2026-01-02T14:00:00Z",
        "events": [
            {
                "provider_event_id": "1:2026-01-02",
                "event_time": "2026-01-02T14:30:00Z",
                "importance": "HIGH",
                "scope": ["USD"],
                "event_code": "US_NFP",
                "name": "Non-Farm Payrolls",
            }
        ],
    }
    _write(path, legacy_shape_payload)

    result = _read(path)

    assert result.data_quality is HighImpactEventDataQuality.MALFORMED
    assert result.events == ()


def test_missing_required_field_is_malformed(tmp_path: Path) -> None:
    path = tmp_path / "calendar.json"
    payload = json.loads(json.dumps(_VALID_PAYLOAD))
    del payload["events"][0]["event_code"]
    _write(path, payload)

    result = _read(path)

    assert result.data_quality is HighImpactEventDataQuality.MALFORMED
    assert result.events == ()


def test_one_malformed_event_discards_the_entire_file_no_partial_trust(tmp_path: Path) -> None:
    path = tmp_path / "calendar.json"
    payload = json.loads(json.dumps(_VALID_PAYLOAD))
    payload["events"].append(
        {
            "provider_event_id": "2:2026-01-02",
            "event_time_server": "2026-01-02T14:30:00",
            "observed_offset_seconds": 0,
            "importance": "NOT_A_REAL_IMPORTANCE",
            "scope": ["USD"],
            "event_code": "FOMC",
            "name": "FOMC Rate Decision",
        }
    )
    _write(path, payload)

    result = _read(path)

    assert result.data_quality is HighImpactEventDataQuality.MALFORMED
    assert result.events == ()  # the one otherwise-valid event is also discarded - no partial trust


def test_naive_generated_at_is_malformed(tmp_path: Path) -> None:
    path = tmp_path / "calendar.json"
    _write(path, dict(_VALID_PAYLOAD, generated_at="2026-01-02T14:00:00"))  # no timezone
    result = _read(path)
    assert result.data_quality is HighImpactEventDataQuality.MALFORMED


def test_deterministic_same_file_same_output(tmp_path: Path) -> None:
    path = tmp_path / "calendar.json"
    _write(path, _VALID_PAYLOAD)

    first = _read(path)
    second = _read(path)
    assert first == second


def test_reader_never_writes_the_file(tmp_path: Path) -> None:
    path = tmp_path / "calendar.json"
    _write(path, _VALID_PAYLOAD)
    original_mtime = path.stat().st_mtime

    _read(path)

    assert path.stat().st_mtime == original_mtime
    assert json.loads(path.read_text(encoding="utf-8")) == _VALID_PAYLOAD


def test_fresh_valid_file_with_zero_events_stays_fresh(tmp_path: Path) -> None:
    """A successful query with zero (mapped) rows is a genuine, current
    fact - distinct from a failed/unavailable read - and must publish/parse
    as FRESH with an empty events tuple, never UNAVAILABLE/MALFORMED."""
    path = tmp_path / "calendar.json"
    _write(path, dict(_VALID_PAYLOAD, events=[]))

    result = _read(path)

    assert result.data_quality is HighImpactEventDataQuality.FRESH
    assert result.events == ()


def test_golden_fixture_matches_documented_wire_shape(tmp_path: Path) -> None:
    """The exact shape documented in this module's own docstring must
    parse successfully end-to-end."""
    path = tmp_path / "calendar.json"
    golden = {
        "schema_version": 2,
        "producer": "mt5_calendar_bridge",
        "generated_at": "2026-09-08T14:00:00Z",
        "events": [
            {
                "provider_event_id": "1234:2026-09-08",
                "event_time_server": "2026-09-08T14:30:00",
                "observed_offset_seconds": 0,
                "importance": "HIGH",
                "scope": ["USD"],
                "event_code": "US_NFP",
                "name": "Non-Farm Payrolls",
            }
        ],
    }
    _write(path, golden)

    result = read_high_impact_event_context(
        path,
        as_of=datetime(2026, 9, 8, 14, 5, 0, tzinfo=UTC),
        staleness_threshold=timedelta(hours=1),
        timezone_config=UTC_TZ_CONFIG,
    )

    assert result.data_quality is HighImpactEventDataQuality.FRESH
    assert result.events[0].provider_event_id == "1234:2026-09-08"
    assert result.events[0].event_time == datetime(2026, 9, 8, 14, 30, 0, tzinfo=UTC)


# --- Timezone design closure: event_time_server -> UTC conversion ---


def test_event_time_server_must_be_naive_aware_value_rejected(tmp_path: Path) -> None:
    """An already tz-aware/``Z``-suffixed ``event_time_server`` must never
    be silently trusted as a proven UTC fact - reject as MALFORMED."""
    path = tmp_path / "calendar.json"
    payload = json.loads(json.dumps(_VALID_PAYLOAD))
    payload["events"][0]["event_time_server"] = "2026-01-02T14:30:00Z"
    _write(path, payload)

    result = _read(path)

    assert result.data_quality is HighImpactEventDataQuality.MALFORMED
    assert result.events == ()


def test_event_time_server_with_explicit_offset_suffix_rejected(tmp_path: Path) -> None:
    path = tmp_path / "calendar.json"
    payload = json.loads(json.dumps(_VALID_PAYLOAD))
    payload["events"][0]["event_time_server"] = "2026-01-02T14:30:00+02:00"
    _write(path, payload)

    result = _read(path)

    assert result.data_quality is HighImpactEventDataQuality.MALFORMED


def test_timezone_config_absent_degrades_to_unavailable_never_fabricates_utc(tmp_path: Path) -> None:
    path = tmp_path / "calendar.json"
    _write(path, _VALID_PAYLOAD)

    result = _read(path, timezone_config=None)

    assert result.data_quality is HighImpactEventDataQuality.UNAVAILABLE
    assert result.events == ()
    assert result.generated_at is None


def test_non_utc_zone_converts_server_local_to_correct_utc_instant(tmp_path: Path) -> None:
    path = tmp_path / "calendar.json"
    payload = json.loads(json.dumps(_VALID_PAYLOAD))
    payload["events"][0]["event_time_server"] = "2026-01-02T16:30:00"  # Europe/Nicosia is UTC+2 in January
    _write(path, payload)

    result = read_high_impact_event_context(
        path,
        as_of=AS_OF,
        staleness_threshold=STALENESS_THRESHOLD,
        timezone_config=HighImpactEventCalendarTimezoneConfig(server_timezone="Europe/Nicosia"),
    )

    assert result.data_quality is HighImpactEventDataQuality.FRESH
    assert result.events[0].event_time == datetime(2026, 1, 2, 14, 30, 0, tzinfo=UTC)


def test_dst_conversion_before_spring_forward_transition(tmp_path: Path) -> None:
    """Europe/Bucharest springs forward on 2026-03-29 at 03:00 local (jumps
    to 04:00, EET +2 -> EEST +3). A naive server-local instant strictly
    before the jump must convert using the pre-transition +2 offset."""
    path = tmp_path / "calendar.json"
    payload = json.loads(json.dumps(_VALID_PAYLOAD))
    payload["events"][0]["event_time_server"] = "2026-03-29T02:30:00"
    _write(path, payload)

    result = read_high_impact_event_context(
        path,
        as_of=AS_OF,
        staleness_threshold=STALENESS_THRESHOLD,
        timezone_config=HighImpactEventCalendarTimezoneConfig(server_timezone="Europe/Bucharest"),
    )

    assert result.events[0].event_time == datetime(2026, 3, 29, 0, 30, 0, tzinfo=UTC)


def test_dst_conversion_after_spring_forward_transition(tmp_path: Path) -> None:
    """A naive server-local instant strictly after the same jump must
    convert using the post-transition +3 offset - proving the chosen
    zoneinfo-based strategy is correct on BOTH sides of a future DST
    transition, which naive current-offset arithmetic cannot guarantee."""
    path = tmp_path / "calendar.json"
    payload = json.loads(json.dumps(_VALID_PAYLOAD))
    payload["events"][0]["event_time_server"] = "2026-03-29T04:30:00"
    _write(path, payload)

    result = read_high_impact_event_context(
        path,
        as_of=AS_OF,
        staleness_threshold=STALENESS_THRESHOLD,
        timezone_config=HighImpactEventCalendarTimezoneConfig(server_timezone="Europe/Bucharest"),
    )

    assert result.events[0].event_time == datetime(2026, 3, 29, 1, 30, 0, tzinfo=UTC)


def test_normal_unambiguous_timestamp_near_transition_converts(tmp_path: Path) -> None:
    """A naive local instant with a genuinely single UTC interpretation
    (well clear of the gap/fold hour) must still convert normally, even on
    the same calendar day as a transition."""
    path = tmp_path / "calendar.json"
    payload = json.loads(json.dumps(_VALID_PAYLOAD))
    payload["events"][0]["event_time_server"] = "2026-03-29T10:00:00"  # well after the 03:00-04:00 gap, +3 offset
    _write(path, payload)

    result = read_high_impact_event_context(
        path,
        as_of=AS_OF,
        staleness_threshold=STALENESS_THRESHOLD,
        timezone_config=HighImpactEventCalendarTimezoneConfig(server_timezone="Europe/Bucharest"),
    )

    assert result.data_quality is HighImpactEventDataQuality.FRESH
    assert result.events[0].event_time == datetime(2026, 3, 29, 7, 0, 0, tzinfo=UTC)


def test_spring_forward_nonexistent_local_timestamp_is_rejected(tmp_path: Path) -> None:
    """Europe/Bucharest jumps from local 03:00 straight to 04:00 on
    2026-03-29 (confirmed via direct zoneinfo transition scan: the UTC
    offset changes from +2 to +3 at 2026-03-29T01:00:00Z). The naive local
    wall-clock value 03:30 therefore never occurs - reject, never
    fabricate a UTC instant for it."""
    path = tmp_path / "calendar.json"
    payload = json.loads(json.dumps(_VALID_PAYLOAD))
    payload["events"][0]["event_time_server"] = "2026-03-29T03:30:00"
    _write(path, payload)

    result = read_high_impact_event_context(
        path,
        as_of=AS_OF,
        staleness_threshold=STALENESS_THRESHOLD,
        timezone_config=HighImpactEventCalendarTimezoneConfig(server_timezone="Europe/Bucharest"),
    )

    assert result.data_quality is HighImpactEventDataQuality.MALFORMED
    assert result.events == ()


def test_fall_back_ambiguous_local_timestamp_is_rejected(tmp_path: Path) -> None:
    """Europe/Bucharest falls back from local 04:00 to 03:00 on
    2026-10-25 (confirmed via direct zoneinfo transition scan: the UTC
    offset changes from +3 to +2 at 2026-10-25T01:00:00Z). The naive local
    wall-clock value 03:30 therefore occurs TWICE, at two different UTC
    instants (2026-10-25T00:30:00Z and 2026-10-25T01:30:00Z) - reject
    rather than silently choosing fold=0 or fold=1."""
    path = tmp_path / "calendar.json"
    payload = json.loads(json.dumps(_VALID_PAYLOAD))
    payload["events"][0]["event_time_server"] = "2026-10-25T03:30:00"
    _write(path, payload)

    result = read_high_impact_event_context(
        path,
        as_of=AS_OF,
        staleness_threshold=STALENESS_THRESHOLD,
        timezone_config=HighImpactEventCalendarTimezoneConfig(server_timezone="Europe/Bucharest"),
    )

    assert result.data_quality is HighImpactEventDataQuality.MALFORMED
    assert result.events == ()


def test_ambiguous_rejection_never_silently_picks_either_fold_interpretation(tmp_path: Path) -> None:
    """Belt-and-suspenders: neither of the two real, valid UTC instants
    that the ambiguous local timestamp above could have meant is ever
    produced - the whole file is discarded, not narrowed to one guess."""
    path = tmp_path / "calendar.json"
    payload = json.loads(json.dumps(_VALID_PAYLOAD))
    payload["events"][0]["event_time_server"] = "2026-10-25T03:30:00"
    _write(path, payload)

    result = read_high_impact_event_context(
        path,
        as_of=AS_OF,
        staleness_threshold=STALENESS_THRESHOLD,
        timezone_config=HighImpactEventCalendarTimezoneConfig(server_timezone="Europe/Bucharest"),
    )

    assert result.events == ()
    fold_0_guess = datetime(2026, 10, 25, 0, 30, 0, tzinfo=UTC)
    fold_1_guess = datetime(2026, 10, 25, 1, 30, 0, tzinfo=UTC)
    assert fold_0_guess not in [e.event_time for e in result.events]
    assert fold_1_guess not in [e.event_time for e in result.events]


def test_observed_offset_seconds_never_affects_conversion(tmp_path: Path) -> None:
    """``observed_offset_seconds`` is audit-only. A wildly wrong value must
    have zero effect on the computed UTC ``event_time`` - only
    ``server_timezone`` drives the conversion."""
    path = tmp_path / "calendar.json"
    payload = json.loads(json.dumps(_VALID_PAYLOAD))
    payload["events"][0]["observed_offset_seconds"] = 999999  # nonsensical, must be ignored
    _write(path, payload)

    result = _read(path)

    assert result.events[0].event_time == datetime(2026, 1, 2, 14, 30, 0, tzinfo=UTC)


def test_observed_offset_seconds_missing_is_malformed(tmp_path: Path) -> None:
    path = tmp_path / "calendar.json"
    payload = json.loads(json.dumps(_VALID_PAYLOAD))
    del payload["events"][0]["observed_offset_seconds"]
    _write(path, payload)

    result = _read(path)

    assert result.data_quality is HighImpactEventDataQuality.MALFORMED


def test_observed_offset_seconds_wrong_type_is_malformed(tmp_path: Path) -> None:
    path = tmp_path / "calendar.json"
    payload = json.loads(json.dumps(_VALID_PAYLOAD))
    payload["events"][0]["observed_offset_seconds"] = "0"
    _write(path, payload)

    result = _read(path)

    assert result.data_quality is HighImpactEventDataQuality.MALFORMED
