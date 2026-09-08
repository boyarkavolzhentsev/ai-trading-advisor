"""MQL5 calendar bridge file-reader tests (Corrective V1 Integration, test
groups AA/AB/AC + AD determinism, no-write/no-MT5 hygiene)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.core.enums.high_impact_event import HighImpactEventDataQuality
from app.high_impact_event_bridge.file_reader import read_high_impact_event_context

AS_OF = datetime(2026, 1, 2, 14, 30, 0, tzinfo=UTC)
STALENESS_THRESHOLD = timedelta(hours=1)

_VALID_PAYLOAD = {
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


def _write(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_missing_file_is_unavailable(tmp_path: Path) -> None:
    result = read_high_impact_event_context(tmp_path / "absent.json", as_of=AS_OF, staleness_threshold=STALENESS_THRESHOLD)
    assert result.data_quality is HighImpactEventDataQuality.UNAVAILABLE
    assert result.events == ()
    assert result.generated_at is None


def test_fresh_valid_file_parses_correctly(tmp_path: Path) -> None:
    path = tmp_path / "calendar.json"
    _write(path, _VALID_PAYLOAD)

    result = read_high_impact_event_context(path, as_of=AS_OF, staleness_threshold=STALENESS_THRESHOLD)

    assert result.data_quality is HighImpactEventDataQuality.FRESH
    assert result.producer == "mt5_calendar_bridge"
    assert result.generated_at == datetime(2026, 1, 2, 14, 0, 0, tzinfo=UTC)
    assert len(result.events) == 1
    event = result.events[0]
    assert event.provider_event_id == "1:2026-01-02"
    assert event.event_code == "US_NFP"
    assert event.importance.value == "HIGH"
    assert event.scope == ("USD",)


def test_stale_generated_at_fails_open_with_no_events(tmp_path: Path) -> None:
    path = tmp_path / "calendar.json"
    payload = dict(_VALID_PAYLOAD, generated_at="2026-01-02T12:00:00Z")  # 2h30m before AS_OF, threshold is 1h
    _write(path, payload)

    result = read_high_impact_event_context(path, as_of=AS_OF, staleness_threshold=STALENESS_THRESHOLD)

    assert result.data_quality is HighImpactEventDataQuality.STALE
    assert result.events == ()
    assert result.generated_at == datetime(2026, 1, 2, 12, 0, 0, tzinfo=UTC)


def test_malformed_json_is_malformed(tmp_path: Path) -> None:
    path = tmp_path / "calendar.json"
    path.write_text("{not valid json", encoding="utf-8")

    result = read_high_impact_event_context(path, as_of=AS_OF, staleness_threshold=STALENESS_THRESHOLD)

    assert result.data_quality is HighImpactEventDataQuality.MALFORMED
    assert result.events == ()
    assert result.generated_at is None


def test_wrong_schema_version_is_malformed(tmp_path: Path) -> None:
    path = tmp_path / "calendar.json"
    _write(path, dict(_VALID_PAYLOAD, schema_version=2))

    result = read_high_impact_event_context(path, as_of=AS_OF, staleness_threshold=STALENESS_THRESHOLD)

    assert result.data_quality is HighImpactEventDataQuality.MALFORMED


def test_missing_required_field_is_malformed(tmp_path: Path) -> None:
    path = tmp_path / "calendar.json"
    payload = json.loads(json.dumps(_VALID_PAYLOAD))
    del payload["events"][0]["event_code"]
    _write(path, payload)

    result = read_high_impact_event_context(path, as_of=AS_OF, staleness_threshold=STALENESS_THRESHOLD)

    assert result.data_quality is HighImpactEventDataQuality.MALFORMED
    assert result.events == ()


def test_one_malformed_event_discards_the_entire_file_no_partial_trust(tmp_path: Path) -> None:
    path = tmp_path / "calendar.json"
    payload = json.loads(json.dumps(_VALID_PAYLOAD))
    payload["events"].append(
        {
            "provider_event_id": "2:2026-01-02",
            "event_time": "2026-01-02T14:30:00Z",
            "importance": "NOT_A_REAL_IMPORTANCE",
            "scope": ["USD"],
            "event_code": "FOMC",
            "name": "FOMC Rate Decision",
        }
    )
    _write(path, payload)

    result = read_high_impact_event_context(path, as_of=AS_OF, staleness_threshold=STALENESS_THRESHOLD)

    assert result.data_quality is HighImpactEventDataQuality.MALFORMED
    assert result.events == ()  # the one otherwise-valid event is also discarded - no partial trust


def test_naive_timestamp_is_malformed(tmp_path: Path) -> None:
    path = tmp_path / "calendar.json"
    _write(path, dict(_VALID_PAYLOAD, generated_at="2026-01-02T14:00:00"))  # no timezone
    result = read_high_impact_event_context(path, as_of=AS_OF, staleness_threshold=STALENESS_THRESHOLD)
    assert result.data_quality is HighImpactEventDataQuality.MALFORMED


def test_deterministic_same_file_same_output(tmp_path: Path) -> None:
    path = tmp_path / "calendar.json"
    _write(path, _VALID_PAYLOAD)

    first = read_high_impact_event_context(path, as_of=AS_OF, staleness_threshold=STALENESS_THRESHOLD)
    second = read_high_impact_event_context(path, as_of=AS_OF, staleness_threshold=STALENESS_THRESHOLD)
    assert first == second


def test_reader_never_writes_the_file(tmp_path: Path) -> None:
    path = tmp_path / "calendar.json"
    _write(path, _VALID_PAYLOAD)
    original_mtime = path.stat().st_mtime

    read_high_impact_event_context(path, as_of=AS_OF, staleness_threshold=STALENESS_THRESHOLD)

    assert path.stat().st_mtime == original_mtime
    assert json.loads(path.read_text(encoding="utf-8")) == _VALID_PAYLOAD
