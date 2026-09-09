"""Local JSON file reader for the MQL5 economic-calendar bridge.

Expected file shape (produced by an external MQL5 Expert Advisor, never by
this module - this reader never writes a file and never calls MT5/
MetaTrader5 in any way):

    {
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
          "name": "Non-Farm Payrolls"
        }
      ]
    }

``schema_version`` is ``2`` - incremented from the earlier, now-retired ``1``
shape (which carried an already-aware ``event_time`` field) because the
timezone-safety corrective closure changed the wire shape in a genuinely
incompatible way (``event_time`` -> ``event_time_server`` +
``observed_offset_seconds``). A ``schema_version: 1`` payload is rejected
as ``MALFORMED`` outright - no compatibility guessing, no dual-shape
parsing.

``generated_at`` (embedded, producer-authored) is the sole authority for
freshness - never OS file mtime, which this reader does not consult at all
(mirrors ``received_at``/``fetched_at`` conventions used by every existing
Foundation provenance model in this repository; mtime remains available to
an operator via the file's own OS stat as a secondary, out-of-band signal,
but is never read here).

``event_time_server`` is the trade-server-LOCAL wall clock reported by
``MqlCalendarValue.time`` - deliberately naive (no timezone suffix). MQL5
exposes no API that proves what UTC offset applies to an *arbitrary future*
server-local instant (see the approved timezone design closure): the EA
never claims this value is UTC, and this reader never treats it as UTC
either. Converting it to the aware ``HighImpactEventRecord.event_time`` this
reader must produce requires an operator-declared
``HighImpactEventCalendarTimezoneConfig.server_timezone`` (an IANA zone
name) - ``zoneinfo`` carries that zone's own forward-published DST
transition schedule, which is what actually makes an arbitrary-future
conversion sound; nothing in MQL5 itself can. ``observed_offset_seconds`` is
carried for operator audit/drift-detection only (e.g. "does the live
observed offset ever disagree with what the configured zone predicts for
now") and is NEVER read by this reader's conversion path.

Atomicity assumption: this reader assumes the EA-side writer uses a
write-to-temp-then-rename protocol so that any file this reader opens is
already a complete, non-partial write - this module cannot itself detect a
torn write mid-read and does not attempt to (no file locking, no retry).

No partial trust: any parse failure - missing file, invalid JSON, an
unexpected ``schema_version``, a missing/malformed top-level field, or one
malformed event record - discards the ENTIRE file's ``events`` and reports
``MALFORMED``, never a partially-accepted event list.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from app.core.config.high_impact_event_bridge import HighImpactEventCalendarTimezoneConfig
from app.core.enums.high_impact_event import HighImpactEventDataQuality, HighImpactEventImportance
from app.core.models.base import Timestamp
from app.core.models.high_impact_event import HighImpactEventContext, HighImpactEventRecord

_SUPPORTED_SCHEMA_VERSION = 2
_DEFAULT_PRODUCER_FALLBACK = "mt5_calendar_bridge"


def _parse_timestamp(raw: object) -> Timestamp:
    if not isinstance(raw, str) or not raw:
        raise ValueError("timestamp must be a non-empty string")
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return parsed


def _parse_naive_server_timestamp(raw: object) -> datetime:
    """Parse ``event_time_server``: must be a naive (no timezone suffix)
    ISO-8601 string - an already-aware value here would mean the EA (or a
    tampered file) is claiming a UTC/offset fact this reader must never
    trust unverified, so it is rejected rather than silently accepted."""
    if not isinstance(raw, str) or not raw:
        raise ValueError("event_time_server must be a non-empty string")
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is not None:
        raise ValueError("event_time_server must be naive (trade-server-local, no timezone suffix)")
    return parsed


def _resolve_unambiguous_utc(naive_server_time: datetime, zone: ZoneInfo) -> Timestamp:
    """Deterministic, fold-aware validation of one naive server-local
    instant - never silently picks ``fold=0``/``fold=1`` (never uses
    ``observed_offset_seconds`` to choose either, which stays audit-only).

    Compares both PEP 495 fold interpretations of the same naive value:

    - identical UTC offset under both folds -> an ordinary, unambiguous
      instant; convert normally.
    - differing offsets -> either a spring-forward gap (this local wall
      time never occurs) or a fall-back fold (it occurs twice, at two
      different UTC instants) - distinguished by round-tripping each
      candidate UTC instant back through the same zone: an occurring
      instant round-trips to the original naive value, a gap instant
      round-trips to neither fold. Either way this is rejected - never
      fabricated - by raising ``ValueError``, which ``_parse_event``'s
      caller already treats as a whole-file ``MALFORMED`` result.
    """
    fold_0 = naive_server_time.replace(tzinfo=zone, fold=0)
    fold_1 = naive_server_time.replace(tzinfo=zone, fold=1)

    if fold_0.utcoffset() == fold_1.utcoffset():
        return fold_0.astimezone(ZoneInfo("UTC"))

    utc_0 = fold_0.astimezone(ZoneInfo("UTC"))
    utc_1 = fold_1.astimezone(ZoneInfo("UTC"))
    round_trips_0 = utc_0.astimezone(zone).replace(tzinfo=None) == naive_server_time
    round_trips_1 = utc_1.astimezone(zone).replace(tzinfo=None) == naive_server_time

    if round_trips_0 and round_trips_1:
        raise ValueError("event_time_server is ambiguous under server_timezone (DST fall-back fold) - refusing to guess")
    raise ValueError("event_time_server does not exist under server_timezone (DST spring-forward gap)")


def _convert_server_time_to_utc(naive_server_time: datetime, timezone_config: HighImpactEventCalendarTimezoneConfig) -> Timestamp:
    """The one place a real conversion happens - DST-safe for arbitrary
    future dates because ``zoneinfo`` carries the configured IANA zone's own
    forward-published transition schedule (unlike any MQL5-side offset
    arithmetic, which only ever knows the offset valid *right now*)."""
    zone = ZoneInfo(timezone_config.server_timezone)
    return _resolve_unambiguous_utc(naive_server_time, zone)


def _parse_event(raw: object, *, timezone_config: HighImpactEventCalendarTimezoneConfig) -> HighImpactEventRecord:
    if not isinstance(raw, dict):
        raise ValueError("event record must be a JSON object")
    scope_raw = raw.get("scope", ())
    if not isinstance(scope_raw, list):
        raise ValueError("event.scope must be a list when present")
    if not isinstance(raw.get("observed_offset_seconds"), int):
        raise ValueError("event.observed_offset_seconds must be an int (audit-only, never used for conversion)")
    naive_server_time = _parse_naive_server_timestamp(raw["event_time_server"])
    return HighImpactEventRecord(
        provider_event_id=raw["provider_event_id"],
        event_time=_convert_server_time_to_utc(naive_server_time, timezone_config),
        importance=HighImpactEventImportance(raw["importance"]),
        scope=tuple(scope_raw),
        event_code=raw["event_code"],
        name=raw["name"],
    )


def _malformed(producer_fallback: str) -> HighImpactEventContext:
    return HighImpactEventContext(
        events=(), data_quality=HighImpactEventDataQuality.MALFORMED, producer=producer_fallback, generated_at=None
    )


def read_high_impact_event_context(
    path: Path,
    *,
    as_of: Timestamp,
    staleness_threshold: timedelta,
    timezone_config: HighImpactEventCalendarTimezoneConfig | None = None,
    producer_fallback: str = _DEFAULT_PRODUCER_FALLBACK,
) -> HighImpactEventContext:
    """Read and normalize one bridge file into a ``HighImpactEventContext``.

    Deterministic, synchronous, read-only: performs exactly one file read
    and no other I/O. ``as_of`` is caller-supplied, never the wall clock.

    ``timezone_config`` is the operator's IANA-zone attestation for the
    bridge's trade-server clock (see ``HighImpactEventCalendarTimezoneConfig``)
    - without it, no ``event_time_server`` value can be soundly converted to
    UTC, so this reader never guesses: it reports ``UNAVAILABLE`` without
    even opening the file, identically to a missing file.
    """
    if timezone_config is None:
        return HighImpactEventContext(
            events=(), data_quality=HighImpactEventDataQuality.UNAVAILABLE, producer=producer_fallback, generated_at=None
        )

    if not path.is_file():
        return HighImpactEventContext(
            events=(), data_quality=HighImpactEventDataQuality.UNAVAILABLE, producer=producer_fallback, generated_at=None
        )

    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("bridge file root must be a JSON object")
        if payload.get("schema_version") != _SUPPORTED_SCHEMA_VERSION:
            raise ValueError("unsupported or missing schema_version")

        producer = payload["producer"]
        if not isinstance(producer, str) or not producer:
            raise ValueError("producer must be a non-empty string")

        generated_at = _parse_timestamp(payload["generated_at"])

        raw_events = payload["events"]
        if not isinstance(raw_events, list):
            raise ValueError("events must be a list")
        events = tuple(_parse_event(raw, timezone_config=timezone_config) for raw in raw_events)
    except Exception:
        return _malformed(producer_fallback)

    if as_of - generated_at > staleness_threshold:
        return HighImpactEventContext(
            events=(), data_quality=HighImpactEventDataQuality.STALE, producer=producer, generated_at=generated_at
        )

    return HighImpactEventContext(
        events=events, data_quality=HighImpactEventDataQuality.FRESH, producer=producer, generated_at=generated_at
    )


__all__ = ["read_high_impact_event_context"]
