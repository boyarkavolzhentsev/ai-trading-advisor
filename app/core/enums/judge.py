"""Judge verdict enum."""

from __future__ import annotations

from enum import StrEnum


class JudgeVerdictType(StrEnum):
    """Final review outcome produced by the independent judge component."""

    APPROVE = "APPROVE"
    REJECT = "REJECT"
    WAIT = "WAIT"
