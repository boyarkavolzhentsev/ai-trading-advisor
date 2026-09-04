"""Setup Construction vocabulary.

Setup Construction is the deterministic bridge between an already-authorized
directional Policy-eligible ``StrategyFamily`` and the price/risk facts Stage
7 ``CandidateRiskInput`` and later Stage 10C/10E require. No member here
decides LONG vs SHORT (Judge's exclusive authority), ranks strategies,
allocates monetary risk, or sizes broker volume.
"""

from __future__ import annotations

from enum import StrEnum


class SetupConstructionOutcome(StrEnum):
    """Coarse result of one Policy-eligible family's setup construction
    attempt."""

    CONSTRUCTED = "CONSTRUCTED"
    BLOCKED = "BLOCKED"


class SetupBlockReason(StrEnum):
    """Why one Policy-eligible family's setup could not be constructed.

    ``FAMILY_SETUP_UNAVAILABLE`` applies to a family with no approved V1
    setup rule at all (``MEAN_REVERSION``, ``EVENT_DRIVEN``) - no fact is
    even inspected for these. ``MISSING_STOP_REFERENCE`` applies when the
    shared M15 structure fact is itself usable but does not contain the
    specific swing/break this family's rule needs, or when a BREAKOUT
    candidate's latest confirmed break direction disagrees with the
    already-authorized Judge thesis. ``INVALID_STOP_SIDE`` applies when a
    resolved structural level sits on the wrong side of the resolved entry
    price. ``SHARED_FACT_UNAVAILABLE`` applies to the two facts every
    structure-capable family equally depends on: MT5 symbol facts (missing,
    or invalid tick economics) and the M15 market-structure block itself
    (missing, or below approved quality) - never fabricated, never treated
    as a per-family reason.
    """

    FAMILY_SETUP_UNAVAILABLE = "FAMILY_SETUP_UNAVAILABLE"
    MISSING_STOP_REFERENCE = "MISSING_STOP_REFERENCE"
    INVALID_STOP_SIDE = "INVALID_STOP_SIDE"
    SHARED_FACT_UNAVAILABLE = "SHARED_FACT_UNAVAILABLE"


__all__ = ["SetupBlockReason", "SetupConstructionOutcome"]
