"""Stage 10B ``MT5RolloverStatePersistence``: absent/valid/malformed/schema-
invalid/unreadable read semantics, atomic write, write-failure fail-closed
behavior, and prior-valid-state preservation on a failed replace."""

from __future__ import annotations

import os
import stat
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from app.mt5.persistence import MT5RolloverStatePersistence
from tests.mt5_rollover_support import default_rollover_state


def test_read_absent_file_returns_absent(tmp_path: Path) -> None:
    persistence = MT5RolloverStatePersistence(tmp_path / "rollover_state.json")
    status, state = persistence.read()
    assert status == "ABSENT"
    assert state is None


def test_write_then_read_round_trips_exactly(tmp_path: Path) -> None:
    path = tmp_path / "rollover_state.json"
    persistence = MT5RolloverStatePersistence(path)
    original = default_rollover_state(rollover_equity=Decimal("98765.123456789"))

    assert persistence.write(original) is True
    status, state = persistence.read()

    assert status == "VALID"
    assert state == original
    assert state is not None
    assert state.rollover_equity == Decimal("98765.123456789")


def test_write_uses_atomic_replace_no_leftover_temp_file(tmp_path: Path) -> None:
    path = tmp_path / "rollover_state.json"
    persistence = MT5RolloverStatePersistence(path)
    persistence.write(default_rollover_state())
    assert path.exists()
    assert not (tmp_path / "rollover_state.json.tmp").exists()


def test_malformed_json_returns_corrupt(tmp_path: Path) -> None:
    path = tmp_path / "rollover_state.json"
    path.write_text("{not valid json", encoding="utf-8")
    persistence = MT5RolloverStatePersistence(path)

    status, state = persistence.read()
    assert status == "CORRUPT"
    assert state is None


def test_schema_invalid_json_returns_corrupt(tmp_path: Path) -> None:
    path = tmp_path / "rollover_state.json"
    path.write_text('{"trading_day_key": "2026-01-01"}', encoding="utf-8")  # valid JSON, missing required fields
    persistence = MT5RolloverStatePersistence(path)

    status, state = persistence.read()
    assert status == "CORRUPT"
    assert state is None


def test_valid_json_wrong_shape_returns_corrupt(tmp_path: Path) -> None:
    path = tmp_path / "rollover_state.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    persistence = MT5RolloverStatePersistence(path)

    status, state = persistence.read()
    assert status == "CORRUPT"
    assert state is None


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits not enforced the same way on Windows")
def test_unreadable_file_returns_unavailable(tmp_path: Path) -> None:
    path = tmp_path / "rollover_state.json"
    persistence = MT5RolloverStatePersistence(path)
    persistence.write(default_rollover_state())
    os.chmod(path, 0o000)
    try:
        status, state = persistence.read()
        assert status == "UNAVAILABLE"
        assert state is None
    finally:
        os.chmod(path, stat.S_IWUSR | stat.S_IRUSR)


def test_unreadable_directory_path_returns_unavailable(tmp_path: Path) -> None:
    """A path pointing at a directory (not a file) is a legitimate
    unreadable-as-a-file I/O condition, not corruption."""
    directory_path = tmp_path / "rollover_state.json"
    directory_path.mkdir()
    persistence = MT5RolloverStatePersistence(directory_path)

    status, state = persistence.read()
    assert status == "UNAVAILABLE"
    assert state is None


def test_write_failure_does_not_return_usable_result(tmp_path: Path) -> None:
    """Writing into a nonexistent parent directory fails - no silent
    success, no partial state persisted."""
    path = tmp_path / "nonexistent_directory" / "rollover_state.json"
    persistence = MT5RolloverStatePersistence(path)

    assert persistence.write(default_rollover_state()) is False
    assert not path.exists()


def test_failed_write_does_not_corrupt_existing_valid_state(tmp_path: Path) -> None:
    path = tmp_path / "rollover_state.json"
    persistence = MT5RolloverStatePersistence(path)
    original = default_rollover_state(rollover_equity=Decimal("111111"))
    persistence.write(original)

    # Force a failure by making the target directory read-only so os.replace
    # or the temp-file write cannot complete - simulate by pointing the temp
    # write at a location that cannot be created (a directory in its place).
    tmp_marker = tmp_path / "rollover_state.json.tmp"
    tmp_marker.mkdir()  # temp-file path is now a directory - the real write must fail
    try:
        result = persistence.write(default_rollover_state(rollover_equity=Decimal("222222")))
        assert result is False
    finally:
        tmp_marker.rmdir()

    status, state = persistence.read()
    assert status == "VALID"
    assert state is not None
    assert state.rollover_equity == Decimal("111111")  # untouched by the failed write


def test_persistence_has_no_default_path() -> None:
    with pytest.raises(TypeError):
        MT5RolloverStatePersistence()  # type: ignore[call-arg]
