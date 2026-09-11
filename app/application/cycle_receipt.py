"""Cycle-level request idempotency: one durable, atomic claim per
``logical_cycle_id``.

Corrective design closure ("CYCLE-LEVEL IDEMPOTENCY"): ``logical_cycle_id``
denotes ONE logical advisory attempt. Once accepted, the same
``logical_cycle_id`` must never execute a second advisory cycle, regardless
of the first attempt's outcome (``READY``/``NO_TRADE``/``DEGRADED``/
``SERVICE_UNAVAILABLE``) or of an exception/crash after admission. A new
attempt always requires a new ``logical_cycle_id`` - this module never
generates one and never deletes a receipt "to allow retry" (safety over
transparent replay, mirroring ``app.production_advisory.errors.
ProductionAdvisoryDuplicateCycleError``'s own established precedent one
layer down).

Single-state model, deliberately: there is no ``STARTED`` -> ``COMPLETED``
transition and no rewrite after the fact. ``claim()`` performs exactly one
atomic, exclusive file creation (Windows-compatible
``os.O_CREAT | os.O_EXCL | os.O_WRONLY`` - supported identically on both
platforms by CPython's ``os.open``) - the file's mere EXISTENCE is the only
fact this module ever needs: a receipt proves "this logical request was
already admitted," never "the cycle completed successfully." A second
COMPLETED write would only add a second failure window without improving
idempotency, so no such write exists.

Corruption-safety by construction: because ``O_EXCL`` fails on existence
alone, a partially-written or corrupt receipt is indistinguishable, for
admission purposes, from a healthy one - both fail the exclusive-create
attempt and both correctly report ``ALREADY_EXISTS``. No read/parse of the
receipt body is ever needed to make the admission decision, so no
"reinterpret corruption as absent" bug is reachable here at all.

Filename safety: reuses the exact ``[A-Za-z0-9_-]{1,128}`` charset already
enforced upstream by ``app.application.identity.validate_logical_cycle_id``
before this module is ever called - no second identity grammar is invented.
``_is_safe_logical_cycle_id`` below is an independent, defense-in-depth copy
of the identical check every other trade_id-keyed persistence class in this
repository already carries on its own (``app.mt5.recommendation_persistence``/
``app.mt5.recommendation_provenance_persistence``), never imported across
modules, mirroring their own established "never depends on a sibling
persistence module" precedent.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from enum import StrEnum
from pathlib import Path

_SCHEMA_VERSION = 1


class CycleReceiptClaimResult(StrEnum):
    """Outcome of one ``CycleReceiptPersistence.claim()`` call - never a
    third state. ``CREATED`` means this call is the exclusive winner and may
    proceed into exactly one advisory cycle; ``ALREADY_EXISTS`` means some
    prior call (successful, failed, crashed, or racing concurrently) already
    holds this ``logical_cycle_id`` and this call must not run a cycle."""

    CREATED = "CREATED"
    ALREADY_EXISTS = "ALREADY_EXISTS"


def _is_safe_logical_cycle_id(logical_cycle_id: str) -> bool:
    if not logical_cycle_id:
        return False
    if logical_cycle_id in (".", ".."):
        return False
    return os.sep not in logical_cycle_id and (os.altsep is None or os.altsep not in logical_cycle_id)


class CycleReceiptPersistence:
    """Durable, atomic, create-if-absent claim store for
    ``logical_cycle_id`` values - one JSON document per id, at
    ``<directory>/<logical_cycle_id>.json``.

    No default directory, no environment lookup - bootstrap wiring decides
    where the receipt store lives, mirroring every other Stage 10
    persistence class's own established constructor convention
    (``MT5RolloverStatePersistence``/``MT5RecommendationPersistence``).
    """

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def _path_for(self, logical_cycle_id: str) -> Path | None:
        if not _is_safe_logical_cycle_id(logical_cycle_id):
            return None
        return self._directory / f"{logical_cycle_id}.json"

    def claim(self, logical_cycle_id: str, *, accepted_at: datetime) -> CycleReceiptClaimResult:
        """Atomically claim ``logical_cycle_id``, exactly once, forever.

        Creates the receipt directory if it does not yet exist (safe under
        concurrent callers: ``Path.mkdir(parents=True, exist_ok=True)``
        already swallows a losing ``FileExistsError`` race internally).
        The actual claim is one ``os.open(..., O_CREAT | O_EXCL | O_WRONLY)``
        call - the same exclusive-create primitive on both POSIX and
        Windows (CPython maps it to Windows' own atomic ``CREATE_NEW``
        file-creation disposition) - so exactly one caller, in this process
        or any other pointed at the same directory, ever wins for a given
        path. Deliberately never ``os.replace``-based: replace semantics
        would let a second caller silently overwrite the first claimant's
        file, which is the exact race this design forbids.

        A failure writing the JSON body (or ``fsync``) after the exclusive
        create itself already succeeded is swallowed: the id is already
        consumed the instant the file exists, and this method never deletes
        a receipt to "allow retry" (safety over transparent replay). A
        failure *before* exclusive creation succeeds (e.g. the receipt
        directory could not be created, or a permissions error) is not
        caught here and propagates to the caller as a genuine, unexpected
        persistence error.
        """
        self._directory.mkdir(parents=True, exist_ok=True)
        path = self._path_for(logical_cycle_id)
        if path is None:
            # Unreachable in practice: every caller validates logical_cycle_id
            # against [A-Za-z0-9_-]{1,128} before ever calling claim() (see
            # app.application.identity.validate_logical_cycle_id). Fail
            # closed rather than silently allowing an unsafe filename.
            return CycleReceiptClaimResult.ALREADY_EXISTS

        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return CycleReceiptClaimResult.ALREADY_EXISTS

        # From here on, logical_cycle_id is already consumed - the exclusive
        # create already succeeded - so every failure below is swallowed
        # (never re-raised, never deletes the file) rather than reported.
        try:
            handle = os.fdopen(fd, "wb")
        except OSError:
            os.close(fd)
            return CycleReceiptClaimResult.CREATED

        try:
            with handle:
                body = json.dumps(
                    {
                        "schema_version": _SCHEMA_VERSION,
                        "logical_cycle_id": logical_cycle_id,
                        "accepted_at": accepted_at.isoformat(),
                    }
                ).encode("utf-8")
                handle.write(body)
                handle.flush()
                os.fsync(handle.fileno())
        except OSError:
            pass

        return CycleReceiptClaimResult.CREATED


__all__ = ["CycleReceiptClaimResult", "CycleReceiptPersistence"]
