"""Stage 6B Judge enums - direction/outcome/evidence-role vocabulary only.

Judge is the first Decision-layer component allowed to interpret semantic
dimension/value content. Even so, no member here is a generic cross-contour
"positive/negative" vocabulary: ``DirectionalCandidate`` is deliberately a
strict two-value directional fact, readiness/agreement lives entirely in
``JudgeOutcome``, and absence of direction is represented by ``None`` on
``JudgeFamilyResult.direction`` - never a third enum member. Legacy
``TradeDirection``/``JudgeVerdictType`` are not reused: they conflate market
bias, decision-readiness, and final trade authorization in ways this stage
must keep separate.
"""

from __future__ import annotations

from enum import StrEnum


class EvidenceRole(StrEnum):
    """Categorical role of one cited observation within a family's verdict.

    ``PRIMARY`` evidence is what a directional verdict is built from;
    ``CORROBORATING`` evidence can only veto (force ``MIXED`` by disagreeing
    with an otherwise-established direction) - it can never create a
    directional verdict by itself, and it carries no weight or count.
    """

    PRIMARY = "PRIMARY"
    CORROBORATING = "CORROBORATING"


class JudgeContour(StrEnum):
    """Which embedded Stage 5 contour a ``JudgeEvidenceRef`` points into."""

    TECHNICAL = "TECHNICAL"
    FLOW = "FLOW"
    EXTERNAL = "EXTERNAL"


class DirectionalCandidate(StrEnum):
    """A strategy-specific directional reading of allowed evidence.

    Never a trade order, never an execution instruction - an advisory
    interpretation only. Deliberately two-valued: absence of a directional
    reading is ``JudgeFamilyResult.direction is None``, not a third member.
    """

    LONG_CANDIDATE = "LONG_CANDIDATE"
    SHORT_CANDIDATE = "SHORT_CANDIDATE"


class JudgeOutcome(StrEnum):
    """Per-family verdict of evidence interpretation - never an authorization.

    ``DIRECTIONAL`` means the family's evidence rule produced one agreed
    direction. ``MIXED`` means actual conflicting mapped evidence was found.
    ``INSUFFICIENT_EVIDENCE`` means no usable primary evidence exists for
    this family. Never ``APPROVE``/``REJECT``/``WAIT`` - authorization is a
    later layer's responsibility, not Judge's.
    """

    DIRECTIONAL = "DIRECTIONAL"
    MIXED = "MIXED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


__all__ = [
    "DirectionalCandidate",
    "EvidenceRole",
    "JudgeContour",
    "JudgeOutcome",
]
