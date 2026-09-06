"""Stage 10E-adjacent impure local persistence for
``FinalRecommendationProvenance`` (Final Runtime Integration, Part E
corrective design).

An additive sidecar, deliberately separate from ``app.mt5.
recommendation_persistence.MT5RecommendationPersistence`` (Stage 10E's own
``MT5TrackedRecommendation`` store): recommendation provenance (the
``StrategyFamily``/``approved_risk_amount``/``account_currency`` facts that
never survive into ``PositionRecord``/``MT5TrackedRecommendation``) is a
different concern from broker-matching/lifecycle tracking state, and must
never be mixed into the same file/schema - mirrors ``MT5RecommendationPersistence``'s
own identical precedent for keeping rollover state and trade-tracking state
separate, one file over.

One JSON document per ``trade_id`` at ``<directory>/<trade_id>.provenance.json``
- a distinct suffix from Stage 10E's own ``<trade_id>.json``, so both files
coexist safely, side by side, in the same directory without collision.
Atomically replaced on every write; corruption of one recommendation's
provenance document must never threaten any other recommendation's
provenance, nor its sibling ``MT5TrackedRecommendation`` document (isolated
failure domain, same discipline as ``MT5RecommendationPersistence``).

Never raises for a legitimate persistence condition (absent/malformed/
unreadable file) - every such condition becomes a typed
``RecommendationProvenanceReadStatus`` return value, mirroring
``MT5RecommendationPersistence``'s own "typed state, not exception"
discipline. ``ABSENT`` is a legitimate, expected status for any ``trade_id``
created before this feature existed - never fabricated into a guessed/empty
provenance record.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from app.core.models.final_recommendation_provenance import FinalRecommendationProvenance

RecommendationProvenanceReadStatus = Literal["ABSENT", "VALID", "CORRUPT", "UNAVAILABLE"]
"""What ``MT5RecommendationProvenancePersistence.read()`` observed - mirrors
``app.mt5.recommendation_persistence.TrackedRecommendationReadStatus``
exactly."""

_SUFFIX = ".provenance.json"


def _is_safe_trade_id(trade_id: str) -> bool:
    """Identical safety rule to ``app.mt5.recommendation_persistence``'s own
    - kept as an independent copy (never imported cross-module) so each
    persistence class remains fully self-contained, mirroring that module's
    own precedent of never depending on a sibling Stage 10 persistence
    module."""
    if not trade_id:
        return False
    if trade_id in (".", ".."):
        return False
    return os.sep not in trade_id and (os.altsep is None or os.altsep not in trade_id)


class MT5RecommendationProvenancePersistence:
    """Reads/writes one ``FinalRecommendationProvenance`` per ``trade_id``,
    each at ``<directory>/<trade_id>.provenance.json``. No default
    directory, no environment lookup - runtime/orchestration wiring (not yet
    built) decides where the provenance store lives."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def _path_for(self, trade_id: str) -> Path | None:
        if not _is_safe_trade_id(trade_id):
            return None
        return self._directory / f"{trade_id}{_SUFFIX}"

    def read(self, trade_id: str) -> tuple[RecommendationProvenanceReadStatus, FinalRecommendationProvenance | None]:
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
            provenance = FinalRecommendationProvenance.model_validate_json(raw_text)
        except (json.JSONDecodeError, ValidationError):
            return "CORRUPT", None

        return "VALID", provenance

    def write(self, trade_id: str, provenance: FinalRecommendationProvenance) -> bool:
        """Atomic write: temp file, flush, fsync, ``os.replace``. A failure
        at any step leaves the existing valid file (if any) untouched and
        cleans up the temp file where safely possible."""
        path = self._path_for(trade_id)
        if path is None:
            return False

        tmp_path = path.with_name(path.name + ".tmp")
        try:
            with tmp_path.open("w", encoding="utf-8") as handle:
                handle.write(provenance.model_dump_json())
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
        """Every currently-persisted ``trade_id`` with provenance - mirrors
        ``MT5RecommendationPersistence.list_trade_ids()``'s identical
        precedent."""
        try:
            return tuple(sorted(path.name[: -len(_SUFFIX)] for path in self._directory.glob(f"*{_SUFFIX}")))
        except OSError:
            return ()


__all__ = ["MT5RecommendationProvenancePersistence", "RecommendationProvenanceReadStatus"]
