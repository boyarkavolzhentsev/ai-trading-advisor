"""``app.core.time_normalization.resolve_unambiguous_utc`` - the shared,
generalized DST-safe fold-resolution primitive extracted from
``app.high_impact_event_bridge.file_reader``'s originally private
``_resolve_unambiguous_utc``. Reuses the exact same proven Europe/Bucharest
2026-03-29 (spring-forward) / 2026-10-25 (fall-back) transition dates as
``tests/test_high_impact_event_file_reader.py`` for consistency - the
behavior must be identical, since this is a same-behavior extraction, not a
rewrite."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from app.core.time_normalization import resolve_unambiguous_utc

_ZONE = ZoneInfo("Europe/Bucharest")


def test_normal_timestamp_converts_to_exact_utc() -> None:
    result = resolve_unambiguous_utc(datetime(2026, 1, 1, 15, 0, 0), _ZONE)
    assert result == datetime(2026, 1, 1, 13, 0, 0, tzinfo=UTC)  # winter, UTC+2


def test_before_dst_spring_forward_transition_uses_pre_transition_offset() -> None:
    result = resolve_unambiguous_utc(datetime(2026, 3, 29, 2, 30, 0), _ZONE)
    assert result == datetime(2026, 3, 29, 0, 30, 0, tzinfo=UTC)


def test_after_dst_spring_forward_transition_uses_post_transition_offset() -> None:
    result = resolve_unambiguous_utc(datetime(2026, 3, 29, 4, 30, 0), _ZONE)
    assert result == datetime(2026, 3, 29, 1, 30, 0, tzinfo=UTC)


def test_spring_forward_nonexistent_local_time_is_rejected() -> None:
    with pytest.raises(ValueError, match="does not exist"):
        resolve_unambiguous_utc(datetime(2026, 3, 29, 3, 30, 0), _ZONE)


def test_fall_back_ambiguous_local_time_is_rejected() -> None:
    with pytest.raises(ValueError, match="ambiguous"):
        resolve_unambiguous_utc(datetime(2026, 10, 25, 3, 30, 0), _ZONE)


def test_ambiguous_rejection_never_silently_picks_either_fold_interpretation() -> None:
    """Confirms both real fold interpretations genuinely differ (proving the
    ambiguity is real, not a test-setup mistake), then confirms the function
    raises rather than silently returning either one."""
    naive_local = datetime(2026, 10, 25, 3, 30, 0)
    fold_0_utc = naive_local.replace(tzinfo=_ZONE, fold=0).astimezone(UTC)
    fold_1_utc = naive_local.replace(tzinfo=_ZONE, fold=1).astimezone(UTC)
    assert fold_0_utc != fold_1_utc

    with pytest.raises(ValueError):
        resolve_unambiguous_utc(naive_local, _ZONE)
