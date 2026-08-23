"""Deterministic feature-quality verdict enum.

Distinct from ``DataQuality`` (a single boolean-ish verdict about one raw
fetch): ``FeatureQuality`` is a 4-state verdict about one *derived* feature
block, so a consumer can tell "no source data at all" (``UNAVAILABLE``) apart
from "source data present but too old" (``STALE``) apart from "below the
minimum sample requirement" (``PARTIAL``) apart from a trustworthy value
(``VALID``) - including a genuine zero, which is always ``VALID``, never
``UNAVAILABLE``.
"""

from __future__ import annotations

from enum import StrEnum


class FeatureQuality(StrEnum):
    """Verdict of a Stage 2A feature calculator about one computed block."""

    VALID = "VALID"
    PARTIAL = "PARTIAL"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"
