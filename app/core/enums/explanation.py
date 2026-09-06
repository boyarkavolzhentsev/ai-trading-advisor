"""LLM Explanation Layer vocabulary.

Describes only the coarse content/provider outcome of one explanation
attempt for an already-completed ``RuntimeCycleResult`` - never a trading
decision, direction, gate outcome, or lifecycle fact (those remain the
deterministic engine's exclusive vocabulary, reachable unchanged on
``RuntimeCycleResult`` itself).

``ExplanationContentStatus`` and ``ExplanationProviderStatus`` are
deliberately two independent facts, never one conflated field: whether usable
explanation content exists is never the same question as whether the LLM
provider itself succeeded - a provider failure always still produces usable
content via the deterministic fallback formatter (see
``app.orchestration.explanation``), so collapsing the two would incorrectly
report "no explanation available" when a fully factual, template-based one
is actually present.
"""

from __future__ import annotations

from enum import StrEnum


class ExplanationContentStatus(StrEnum):
    """Whether ``ExplanationResult`` carries usable explanation content.

    A single member for V1: the deterministic fallback formatter is a pure,
    always-succeeding function of an already-valid ``ExplanationContext``
    (which always exists, since ``RuntimeCycleResult`` always exists) - a
    genuinely content-unavailable state is not reachable in V1. Kept as an
    explicit typed field (never merely implied by ``ExplanationResult``
    existing at all) so a future API/Telegram consumer can check this fact
    directly rather than inferring it.
    """

    AVAILABLE = "AVAILABLE"


class ExplanationProviderStatus(StrEnum):
    """Whether, and how, the LLM provider itself succeeded this attempt.

    ``provider_status != LLM_SUCCESS`` means the returned
    ``ExplanationResult``'s content came from the deterministic fallback
    formatter, never from the LLM - this is the sole signal for that fact;
    no separate ``used_fallback`` boolean or ``DETERMINISTIC_FALLBACK``
    member exists, since either would be fully redundant with this one.

    ``LLM_UNAVAILABLE`` means the provider call itself could not complete
    (raised) - never retried (see ``app.orchestration.explanation``).
    ``LLM_INVALID_OUTPUT`` means the provider responded on every attempted
    call (at most one retry) but its structured output could not be
    validated against the exact ``ExplanationContext`` sent.
    """

    LLM_SUCCESS = "LLM_SUCCESS"
    LLM_UNAVAILABLE = "LLM_UNAVAILABLE"
    LLM_INVALID_OUTPUT = "LLM_INVALID_OUTPUT"


__all__ = ["ExplanationContentStatus", "ExplanationProviderStatus"]
