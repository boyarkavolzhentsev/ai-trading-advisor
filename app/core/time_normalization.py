"""Generic, provider-agnostic DST-safe local-wall-clock -> UTC conversion.

Extracted from the originally private ``app.high_impact_event_bridge.
file_reader._resolve_unambiguous_utc`` (MQL5 calendar-bridge DST-safety
closure) into a shared primitive: the algorithm carries no domain-specific
policy of its own - it is pure PEP 495 fold-aware ``datetime``/``zoneinfo``
arithmetic - so every consumer that must convert an operator-declared
IANA-zone local wall-clock instant to UTC (the calendar bridge, and the MT5
Price Authority migration's own market-data timestamp normalization) shares
this one implementation rather than maintaining independent copies of the
same fold-resolution logic.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo


def resolve_unambiguous_utc(naive_local: datetime, zone: ZoneInfo) -> datetime:
    """Deterministic, fold-aware conversion of one naive local wall-clock
    instant to UTC - never silently picks ``fold=0``/``fold=1``.

    Compares both PEP 495 fold interpretations of the same naive value:

    - identical UTC offset under both folds -> an ordinary, unambiguous
      instant; convert normally.
    - differing offsets -> either a spring-forward gap (this local wall
      time never occurs) or a fall-back fold (it occurs twice, at two
      different UTC instants) - distinguished by round-tripping each
      candidate UTC instant back through the same zone: an occurring
      instant round-trips to the original naive value, a gap instant
      round-trips to neither fold. Either way this is rejected - never
      fabricated - by raising ``ValueError``.

    Raises:
        ValueError: if ``naive_local`` does not exist under ``zone`` (a DST
            spring-forward gap) or is ambiguous under it (a DST fall-back
            fold).
    """
    fold_0 = naive_local.replace(tzinfo=zone, fold=0)
    fold_1 = naive_local.replace(tzinfo=zone, fold=1)

    if fold_0.utcoffset() == fold_1.utcoffset():
        return fold_0.astimezone(ZoneInfo("UTC"))

    utc_0 = fold_0.astimezone(ZoneInfo("UTC"))
    utc_1 = fold_1.astimezone(ZoneInfo("UTC"))
    round_trips_0 = utc_0.astimezone(zone).replace(tzinfo=None) == naive_local
    round_trips_1 = utc_1.astimezone(zone).replace(tzinfo=None) == naive_local

    if round_trips_0 and round_trips_1:
        raise ValueError("naive_local is ambiguous under zone (DST fall-back fold) - refusing to guess")
    raise ValueError("naive_local does not exist under zone (DST spring-forward gap)")


__all__ = ["resolve_unambiguous_utc"]
