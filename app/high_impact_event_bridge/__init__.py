"""MQL5 economic-calendar file-bridge adapter (Corrective V1 Integration).

Narrow, production-only I/O adapter: reads the local JSON file an external
MQL5 Expert Advisor is expected to write, and normalizes it into one
``HighImpactEventContext``. Never imports ``app.macro`` and never
constructs an ``EconomicEvent`` - this V1 gate needs only scheduled-event
metadata (see the approved design report, "No release-value ingestion in
V1"), not the full economic-calendar contract.
"""

from __future__ import annotations

from app.high_impact_event_bridge.file_reader import read_high_impact_event_context

__all__ = ["read_high_impact_event_context"]
