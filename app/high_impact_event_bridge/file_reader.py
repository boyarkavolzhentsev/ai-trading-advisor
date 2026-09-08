"""Local JSON file reader for the MQL5 economic-calendar bridge.

Expected file shape (produced by an external MQL5 Expert Advisor, never by
this module - this reader never writes a file and never calls MT5/
MetaTrader5 in any way):

    {
      "schema_version": 1,
      "producer": "mt5_calendar_bridge",
      "generated_at": "2026-09-08T14:00:00Z",
      "events": [
        {
          "provider_event_id": "1234:2026-09-08",
          "event_time": "2026-09-08T14:30:00Z",
          "importance": "HIGH",
          "scope": ["USD"],
          "event_code": "US_NFP",
          "name": "Non-Farm Payrolls"
        }
      ]
    }

``generated_at`` (embedded, producer-authored) is the sole authority for
freshness - never OS file mtime, which this reader does not consult at all
(mirrors ``received_at``/``fetched_at`` conventions used by every existing
Foundation provenance model in this repository; mtime remains available to
an operator via the file's own OS stat as a secondary, out-of-band signal,
but is never read here).

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

from app.core.enums.high_impact_event import HighImpactEventDataQuality, HighImpactEventImportance
from app.core.models.base import Timestamp
from app.core.models.high_impact_event import HighImpactEventContext, HighImpactEventRecord

_SUPPORTED_SCHEMA_VERSION = 1
_DEFAULT_PRODUCER_FALLBACK = "mt5_calendar_bridge"


def _parse_timestamp(raw: object) -> Timestamp:
    if not isinstance(raw, str) or not raw:
        raise ValueError("timestamp must be a non-empty string")
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return parsed


def _parse_event(raw: object) -> HighImpactEventRecord:
    if not isinstance(raw, dict):
        raise ValueError("event record must be a JSON object")
    scope_raw = raw.get("scope", ())
    if not isinstance(scope_raw, list):
        raise ValueError("event.scope must be a list when present")
    return HighImpactEventRecord(
        provider_event_id=raw["provider_event_id"],
        event_time=_parse_timestamp(raw["event_time"]),
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
    producer_fallback: str = _DEFAULT_PRODUCER_FALLBACK,
) -> HighImpactEventContext:
    """Read and normalize one bridge file into a ``HighImpactEventContext``.

    Deterministic, synchronous, read-only: performs exactly one file read
    and no other I/O. ``as_of`` is caller-supplied, never the wall clock.
    """
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
        events = tuple(_parse_event(raw) for raw in raw_events)
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
