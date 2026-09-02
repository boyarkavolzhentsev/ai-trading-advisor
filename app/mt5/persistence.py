"""Stage 10B impure local persistence for ``MT5RolloverState``.

The only file in ``app/mt5`` allowed to touch the filesystem for rollover
purposes - ``app.mt5.rollover`` (the pure decision logic) never does. No
database: a single local JSON file, atomically replaced on every write, is
the smallest reliable persistence unit for one small, infrequently-written
record.

Never raises for a legitimate persistence condition (absent/malformed/
unreadable file) - every such condition becomes a typed
``PersistedStateReadStatus``/``bool`` return value, mirroring ``app.mt5.
client``'s own "typed state, not exception" discipline for legitimate
broker/runtime conditions.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import ValidationError

from app.core.models.mt5_rollover import MT5RolloverState
from app.mt5.rollover import PersistedStateReadStatus


class MT5RolloverStatePersistence:
    """Reads/writes one ``MT5RolloverState`` at an explicit, caller-supplied
    ``Path``. No default path, no environment lookup - runtime/orchestration
    wiring (not yet built) decides where the file lives."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def read(self) -> tuple[PersistedStateReadStatus, MT5RolloverState | None]:
        try:
            raw_text = self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return "ABSENT", None
        except OSError:
            return "UNAVAILABLE", None

        try:
            state = MT5RolloverState.model_validate_json(raw_text)
        except (json.JSONDecodeError, ValidationError):
            return "CORRUPT", None

        return "VALID", state

    def write(self, state: MT5RolloverState) -> bool:
        """Atomic write: temp file, flush, fsync, ``os.replace``. A failure
        at any step leaves the existing valid file (if any) untouched and
        cleans up the temp file where safely possible."""
        tmp_path = self._path.with_name(self._path.name + ".tmp")
        try:
            with tmp_path.open("w", encoding="utf-8") as handle:
                handle.write(state.model_dump_json())
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, self._path)
        except OSError:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
            return False
        return True


__all__ = ["MT5RolloverStatePersistence"]
