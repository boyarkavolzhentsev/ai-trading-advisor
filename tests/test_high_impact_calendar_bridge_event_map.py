"""Exact producer-side (event_code, currency, country_code, country_id) ->
canonical mapping table tests for
``mql5/include/HighImpactCalendarBridge_EventMap.mqh`` (Calendar Bridge
mapping closure).

Parses the static ``.mqh`` source text directly (no MetaEditor/MT5
available - see the implementation report's caveat) and checks the exact
entries against the raw MetaQuotes discovery log findings, including the
corrected ``US_CORE_CPI``/``US_ISM`` codes and the explicit exclusion list.
"""

from __future__ import annotations

import re
from pathlib import Path

_EVENT_MAP_SOURCE = Path(__file__).resolve().parent.parent / "mql5" / "include" / "HighImpactCalendarBridge_EventMap.mqh"

_ENTRY_PATTERN = re.compile(
    r'\{\s*"(?P<event_code>[^"]+)"\s*,\s*"(?P<currency>[^"]+)"\s*,\s*"(?P<country_code>[^"]+)"\s*,\s*'
    r"(?P<country_id>\d+)\s*,\s*\"(?P<canonical_code>[^\"]+)\"\s*\}"
)

_EXPECTED_ENTRIES = {
    ("consumer-price-index-mm", "USD", "US", 840): "US_CPI",
    ("consumer-price-index-yy", "USD", "US", 840): "US_CPI",
    ("consumer-price-index-ex-food-energy-mm", "USD", "US", 840): "US_CORE_CPI",
    ("consumer-price-index-ex-food-energy-yy", "USD", "US", 840): "US_CORE_CPI",
    ("pce-price-index-mm", "USD", "US", 840): "US_PCE",
    ("pce-price-index-yy", "USD", "US", 840): "US_PCE",
    ("core-pce-price-index-mm", "USD", "US", 840): "US_CORE_PCE",
    ("core-pce-price-index-yy", "USD", "US", 840): "US_CORE_PCE",
    ("nonfarm-payrolls", "USD", "US", 840): "US_NFP",
    ("unemployment-rate", "USD", "US", 840): "US_UNEMPLOYMENT",
    ("ecb-deposit-rate-decision", "EUR", "EU", 999): "ECB_RATE_DECISION",
    ("ecb-interest-rate-decision", "EUR", "EU", 999): "ECB_RATE_DECISION",
    ("consumer-price-index-yy", "EUR", "EU", 999): "EUROZONE_CPI",
    ("boe-interest-rate-decision", "GBP", "GB", 826): "BOE_RATE_DECISION",
    ("cpi-yy", "GBP", "GB", 826): "UK_CPI",
    ("boj-interest-rate-decision", "JPY", "JP", 392): "BOJ_RATE_DECISION",
    ("eia-crude-oil-stocks-change", "USD", "US", 840): "EIA_CRUDE_INVENTORIES",
    ("gross-domestic-product-qq", "USD", "US", 840): "US_GDP",
    ("ism-manufacturing-pmi", "USD", "US", 840): "US_ISM",
    ("ism-non-manufacturing-pmi", "USD", "US", 840): "US_ISM",
    ("markit-manufacturing-pmi", "USD", "US", 840): "US_MAJOR_PMI",
    ("markit-services-pmi", "USD", "US", 840): "US_MAJOR_PMI",
    ("markit-composite-pmi", "USD", "US", 840): "US_MAJOR_PMI",
    ("fomc-meeting-statement", "USD", "US", 840): "FOMC",
    ("fomc-press-conference", "USD", "US", 840): "FOMC",
}

_EXPECTED_CANONICAL_CODES = {
    "US_CPI",
    "US_CORE_CPI",
    "US_PCE",
    "US_CORE_PCE",
    "US_NFP",
    "US_UNEMPLOYMENT",
    "ECB_RATE_DECISION",
    "EUROZONE_CPI",
    "BOE_RATE_DECISION",
    "UK_CPI",
    "BOJ_RATE_DECISION",
    "EIA_CRUDE_INVENTORIES",
    "US_GDP",
    "US_ISM",
    "US_MAJOR_PMI",
    "FOMC",
}

_EXPLICITLY_EXCLUDED_EVENT_CODES = {
    "marginal-lending-facility-rate-decision",
    "chicago-pmi",
    "fomc-minutes",
    "fomc-economic-projections",
    "ism-services-pmi",  # the rejected, non-existent guess corrected during closure
}


def _parsed_entries() -> dict[tuple[str, str, str, int], str]:
    text = _EVENT_MAP_SOURCE.read_text(encoding="utf-8")
    return {
        (m["event_code"], m["currency"], m["country_code"], int(m["country_id"])): m["canonical_code"]
        for m in _ENTRY_PATTERN.finditer(text)
    }


def test_table_has_exactly_the_approved_entries() -> None:
    assert _parsed_entries() == _EXPECTED_ENTRIES


def test_table_covers_exactly_sixteen_canonical_codes() -> None:
    assert set(_parsed_entries().values()) == _EXPECTED_CANONICAL_CODES
    assert len(_EXPECTED_CANONICAL_CODES) == 16


def test_us_core_cpi_uses_the_recovered_raw_log_codes() -> None:
    entries = _parsed_entries()
    assert entries[("consumer-price-index-ex-food-energy-mm", "USD", "US", 840)] == "US_CORE_CPI"
    assert entries[("consumer-price-index-ex-food-energy-yy", "USD", "US", 840)] == "US_CORE_CPI"


def test_us_ism_uses_corrected_non_manufacturing_code() -> None:
    entries = _parsed_entries()
    assert entries[("ism-non-manufacturing-pmi", "USD", "US", 840)] == "US_ISM"


def test_eurozone_cpi_key_includes_country_id_and_differs_from_us_cpi() -> None:
    entries = _parsed_entries()
    assert entries[("consumer-price-index-yy", "USD", "US", 840)] == "US_CPI"
    assert entries[("consumer-price-index-yy", "EUR", "EU", 999)] == "EUROZONE_CPI"


def test_excluded_event_codes_never_appear_in_the_table() -> None:
    mapped_event_codes = {key[0] for key in _parsed_entries()}
    assert mapped_event_codes.isdisjoint(_EXPLICITLY_EXCLUDED_EVENT_CODES)


def test_no_regex_or_substring_lookup_helpers_in_source() -> None:
    """Comments are stripped first: this file's own explanatory header
    names ``StringFind``/``StringSubstr`` in prose ("No StringFind/
    StringSubstr/regex of any kind") - a plain substring scan cannot tell
    that apart from real code."""
    text = re.sub(r"//.*?$|/\*.*?\*/", "", _EVENT_MAP_SOURCE.read_text(encoding="utf-8"), flags=re.MULTILINE | re.DOTALL)
    for forbidden in ("StringFind", "StringSubstr", ".contains(", "StringToLower", "StringToUpper"):
        assert forbidden not in text
