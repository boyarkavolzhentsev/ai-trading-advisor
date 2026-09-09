"""MQL5 High-Impact Calendar Bridge producer source-hygiene tests.

Text-level checks only (no MetaEditor/MT5 available in this environment -
see the implementation report's explicit caveat) - proves the producer's
source never references any trading/execution/network/DLL/socket surface,
per the approved safety boundary: "Calendar reads + local FILE_COMMON writes
only."
"""

from __future__ import annotations

import re
from pathlib import Path

_COMMENT_PATTERN = re.compile(r"//.*?$|/\*.*?\*/", re.MULTILINE | re.DOTALL)


def _strip_comments(text: str) -> str:
    """Remove ``//`` and ``/* */`` comments before any forbidden-substring
    scan - this module's own explanatory comments name several forbidden
    tokens in prose ("contains no OrderSend... no OnTick...") and a plain
    substring check cannot distinguish that from real code. Mirrors why
    ``tests/test_mt5_rollover_calculation.py``'s hygiene check is AST-based
    rather than substring-based for the same reason in Python source."""
    return _COMMENT_PATTERN.sub("", text)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_EA_SOURCE = _REPO_ROOT / "mql5" / "experts" / "HighImpactCalendarBridge.mq5"
_EVENT_MAP_SOURCE = _REPO_ROOT / "mql5" / "include" / "HighImpactCalendarBridge_EventMap.mqh"

_FORBIDDEN_SUBSTRINGS = (
    "OrderSend",
    "OrderModify",
    "OrderDelete",
    "OrderClose",
    "CTrade",
    "PositionOpen",
    "PositionClose",
    "PositionModify",
    "WebRequest",
    "#import",
    "SocketCreate",
    "SocketConnect",
    "SocketSend",
    "SocketReceive",
    "#include <Trade\\",
)


def _ea_text() -> str:
    return _EA_SOURCE.read_text(encoding="utf-8")


def test_ea_source_file_exists() -> None:
    assert _EA_SOURCE.is_file()


def test_event_map_source_file_exists() -> None:
    assert _EVENT_MAP_SOURCE.is_file()


def test_ea_contains_no_forbidden_trading_or_network_calls() -> None:
    text = _strip_comments(_ea_text())
    for forbidden in _FORBIDDEN_SUBSTRINGS:
        assert forbidden not in text, f"forbidden reference found: {forbidden!r}"


def test_event_map_contains_no_forbidden_trading_or_network_calls() -> None:
    text = _strip_comments(_EVENT_MAP_SOURCE.read_text(encoding="utf-8"))
    for forbidden in _FORBIDDEN_SUBSTRINGS:
        assert forbidden not in text, f"forbidden reference found: {forbidden!r}"


def test_ea_defines_no_ontick_handler() -> None:
    """Read-only EA: no tick-driven behavior of any kind."""
    text = _strip_comments(_ea_text())
    assert "OnTick" not in text


def test_ea_defines_required_lifecycle_handlers_only() -> None:
    text = _ea_text()
    for required in ("int OnInit()", "void OnDeinit(", "void OnTimer()"):
        assert required in text


def test_ea_uses_calendar_read_apis() -> None:
    text = _ea_text()
    for required in ("CalendarValueHistory", "CalendarEventById", "CalendarCountryById"):
        assert required in text


def test_ea_publishes_via_file_common_only() -> None:
    text = _ea_text()
    assert "FILE_COMMON" in text
    assert "FileMove" in text


def test_ea_never_appends_z_to_server_local_time() -> None:
    """The naive server-local formatter must never suffix 'Z' - only the
    separate UTC-'now' formatter (generated_at) may."""
    text = _ea_text()
    naive_fn_start = text.index("string ServerTimeToNaiveIsoText")
    naive_fn_body = text[naive_fn_start : naive_fn_start + 400]
    assert '+ "Z"' not in naive_fn_body
    assert "return text;" in naive_fn_body


def test_ea_generated_at_uses_timegmt_and_z_suffix() -> None:
    text = _ea_text()
    utc_fn_start = text.index("string ServerNowToUtcIsoText")
    utc_fn_body = text[utc_fn_start : utc_fn_start + 400]
    assert "TimeGMT()" in utc_fn_body
    assert '+ "Z"' in utc_fn_body


def test_ea_query_failure_does_not_publish() -> None:
    text = _ea_text()
    failure_branch_start = text.index("if(count < 0)")
    failure_branch = text[failure_branch_start : failure_branch_start + 300]
    assert "return;" in failure_branch
    assert "WriteAndPublishJson" not in failure_branch


def test_ea_observed_offset_is_labelled_audit_only_and_not_reused() -> None:
    text = _ea_text()
    assert "observed_offset_seconds" in text
    # the audit value is computed once and only ever serialized, never fed
    # back into ServerTimeToNaiveIsoText/ServerNowToUtcIsoText.
    assert "observed_offset_seconds" not in text[text.index("string ServerTimeToNaiveIsoText") :]
