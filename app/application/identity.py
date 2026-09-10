"""Application-layer cycle/trade identity policy.

V1 identity policy is singular: the caller owns ``logical_cycle_id`` on
every request. This module never generates one itself (no ``uuid``/
``random``/``secrets``/wall-clock-derived value/``hash()`` anywhere here) -
mirrors ``ProductionAdvisoryComposer``'s own "never generates a trade_id"
discipline one layer up (see ``app.production_advisory.composer``).

``trade_id`` derivation is pure string concatenation, never parsed back into
its components downstream - it remains an opaque identifier to every
persistence/tracking consumer (``MT5RecommendationPersistence``/
``MT5RecommendationProvenancePersistence``), exactly as it is today for any
other caller-supplied trade_id.

Filesystem-safety rationale (why ``__`` and this exact charset): both
``MT5RecommendationPersistence._path_for``/``MT5RecommendationProvenancePersistence._path_for``
build a filename directly from ``trade_id`` (``<trade_id>.json``/
``<trade_id>.provenance.json``) and their shared ``_is_safe_trade_id`` guard
rejects only path separators and the exact strings ``"."``/``".."`` - it does
NOT reject ``:``, which is Windows NTFS Alternate-Data-Stream syntax, not a
normal filename character. This module's own charset
(``[A-Za-z0-9_-]``) excludes ``:``, ``/``, ``\\``, and ``.`` entirely, so a
derived ``trade_id`` can never trigger that gap, independent of any change to
``app.mt5.recommendation_persistence``/``app.mt5.recommendation_provenance_persistence``
themselves (see ``tests/test_application_windows_filesystem_regression.py``
for the direct round-trip proof).

Collision-freedom: ``family.value`` is drawn from the closed, four-member
``StrategyFamily`` enum (``TREND_FOLLOWING``, ``MEAN_REVERSION``,
``BREAKOUT``, ``EVENT_DRIVEN``) - no member is a suffix of another - so two
distinct ``(logical_cycle_id, family)`` pairs can never derive an identical
``trade_id`` string, regardless of any ``_`` sequence embedded in
``logical_cycle_id`` itself. Reversibility is therefore satisfied by "clearly
structured," never by naive re-parsing - nothing in this repository ever
splits a ``trade_id`` back into its components.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from app.core.enums.strategy_router import StrategyFamily

_LOGICAL_CYCLE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
"""Conservative, ASCII-only charset: no path separator, no colon, no dot (so
no traversal token and no accidental match against the ``.tmp``/``.json``/
``.provenance.json`` persistence suffix conventions), no whitespace. Bounded
at 128 characters - see this module's own docstring and
``app/application/identity.py``'s length arithmetic in the approved design
closure (longest derived trade_id stays well under the 255-character
single-filename-component limit any common filesystem enforces)."""


def validate_logical_cycle_id(logical_cycle_id: str) -> None:
    """Raise ``ApplicationInputError`` unless ``logical_cycle_id`` matches
    ``[A-Za-z0-9_-]{1,128}`` exactly - the sole caller-input validation point
    for cycle identity in this package."""
    from app.application.errors import ApplicationInputError

    if not _LOGICAL_CYCLE_ID_PATTERN.fullmatch(logical_cycle_id):
        raise ApplicationInputError(
            "logical_cycle_id must match [A-Za-z0-9_-]{1,128}; got "
            f"{logical_cycle_id!r}"
        )


def derive_trade_id(logical_cycle_id: str, family: StrategyFamily) -> str:
    """Deterministic ``trade_id`` for one ``(logical_cycle_id, family)``
    pair - pure string concatenation, no randomness, no ``hash()``."""
    return f"{logical_cycle_id}__{family.value}"


def derive_trade_ids(logical_cycle_id: str) -> Mapping[StrategyFamily, str]:
    """Complete ``trade_ids`` mapping covering every ``StrategyFamily`` -
    satisfies ``ProductionAdvisoryComposer.run_cycle``'s own coverage
    requirement (``_validate_trade_id_coverage``) by construction."""
    return {family: derive_trade_id(logical_cycle_id, family) for family in StrategyFamily}


__all__ = ["derive_trade_id", "derive_trade_ids", "validate_logical_cycle_id"]
