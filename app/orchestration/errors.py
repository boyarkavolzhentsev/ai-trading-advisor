"""Orchestration input-validation errors.

Every error here signals a programming/orchestration mistake in how a
caller-supplied fact was assembled and handed to an
``app.orchestration`` integration function - never a legitimate market or
account-risk condition. Mirrors ``app.risk.errors``/``app.market_evaluation.
errors`` one architectural layer over.
"""

from __future__ import annotations


class FinalRecommendationInputError(ValueError):
    """Base class for all Final Recommendation input-contract violations."""


class MissingTradeIdForActionableFamilyError(FinalRecommendationInputError):
    """Raised when a family that reaches recommendation construction (i.e. is
    not already blocked before Stage 10C sizing) has no matching entry in the
    caller-supplied ``trade_ids`` mapping.

    ``trade_id`` is runtime-owned, caller-supplied identity - never generated
    inside this pure module. A missing entry is a caller-contract violation,
    never a market/business block reason: it is never disguised as
    ``FinalRecommendationBlockReason.SIZING_NOT_ACTIONABLE`` or silently
    skipped.
    """


__all__ = ["FinalRecommendationInputError", "MissingTradeIdForActionableFamilyError"]
