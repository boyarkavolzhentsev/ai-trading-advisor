"""Stage 10E impure local persistence for ``MT5TrackedRecommendation``.

The only Stage 10E module allowed to touch the filesystem - ``app.mt5.
matching``/``app.mt5.tracker`` (the pure decision/reconstruction logic)
never do. One JSON document per ``trade_id``, atomically replaced on every
write, in a caller-supplied directory - deliberately not one consolidated
file: corruption of a single recommendation's document must never threaten
any other recommendation's persisted state (the same isolation-of-failure-
domain discipline Stage 10D's own fail-closed assessments already apply per
deal/day, applied here per trade_id). Deliberately a separate file/schema
from ``app.mt5.persistence`` (Stage 10B's rollover-state store): trade-
tracking state and rollover state are never mixed.

Never raises for a legitimate persistence condition (absent/malformed/
unreadable file) - every such condition becomes a typed
``TrackedRecommendationReadStatus`` return value, mirroring ``app.mt5.
persistence.MT5RolloverStatePersistence``'s own "typed state, not
exception" discipline.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from app.core.models.mt5_tracking import MT5TrackedRecommendation

TrackedRecommendationReadStatus = Literal["ABSENT", "VALID", "CORRUPT", "UNAVAILABLE"]
"""What ``MT5RecommendationPersistence.read()`` observed - mirrors ``app.mt5.
rollover.PersistedStateReadStatus`` exactly."""


def _is_safe_trade_id(trade_id: str) -> bool:
    """A ``trade_id`` becomes a filename component - reject anything that
    could escape the tracking directory (path separators, empty string) or
    collide with the ``.tmp`` suffix convention, rather than silently
    sanitizing it into a different identity."""
    if not trade_id:
        return False
    if trade_id in (".", ".."):
        return False
    return os.sep not in trade_id and (os.altsep is None or os.altsep not in trade_id)


class MT5RecommendationPersistence:
    """Reads/writes one ``MT5TrackedRecommendation`` per ``trade_id``, each
    at ``<directory>/<trade_id>.json``. No default directory, no environment
    lookup - runtime/orchestration wiring (not yet built) decides where the
    tracking store lives."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def _path_for(self, trade_id: str) -> Path | None:
        if not _is_safe_trade_id(trade_id):
            return None
        return self._directory / f"{trade_id}.json"

    def read(self, trade_id: str) -> tuple[TrackedRecommendationReadStatus, MT5TrackedRecommendation | None]:
        path = self._path_for(trade_id)
        if path is None:
            return "UNAVAILABLE", None

        try:
            raw_text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return "ABSENT", None
        except OSError:
            return "UNAVAILABLE", None

        try:
            tracked = MT5TrackedRecommendation.model_validate_json(raw_text)
        except (json.JSONDecodeError, ValidationError):
            return "CORRUPT", None

        return "VALID", tracked

    def write(self, trade_id: str, tracked: MT5TrackedRecommendation) -> bool:
        """Atomic write: temp file, flush, fsync, ``os.replace``. A failure
        at any step leaves the existing valid file (if any) untouched and
        cleans up the temp file where safely possible."""
        path = self._path_for(trade_id)
        if path is None:
            return False

        tmp_path = path.with_name(path.name + ".tmp")
        try:
            with tmp_path.open("w", encoding="utf-8") as handle:
                handle.write(tracked.model_dump_json())
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, path)
        except OSError:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
            return False
        return True

    def list_trade_ids(self) -> tuple[str, ...]:
        """Every currently-persisted ``trade_id`` - the narrowest fact a
        caller needs to enumerate every tracked recommendation (e.g. to
        gather ``already_claimed_position_ids`` across all of them, or to
        assemble a ``tuple[PositionRecord, ...]`` for ``StatisticsAggregator``)
        without this module ever invoking either itself."""
        try:
            return tuple(sorted(path.stem for path in self._directory.glob("*.json")))
        except OSError:
            return ()


__all__ = ["MT5RecommendationPersistence", "TrackedRecommendationReadStatus"]
