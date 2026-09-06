"""Uniform entry point any LLM explanation provider implements.

Mirrors ``app.mt5.protocols.MT5ClientProtocol`` one architectural layer over:
a narrow, explicit surface a fake implementation can satisfy without any
real LLM SDK installed, so every explanation-layer test and every future
concrete provider adapter depends on this protocol, never on a vendor SDK
directly. No provider (OpenAI, Anthropic, or otherwise) is imported here or
anywhere in ``app.orchestration.explanation`` - this module declares no
networking of any kind.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.core.models.explanation import ExplanationLLMResponse, ExplanationRequest


@runtime_checkable
class ExplanationLLMClient(Protocol):
    """One explanation-provider call.

    ``explain`` returns ``ExplanationLLMResponse(narrative=None)`` when the
    provider responded but its raw output could not be parsed/validated
    into ``ExplanationNarrative``'s schema - a normal, non-exceptional
    outcome. A provider call that cannot complete at all (network failure,
    timeout, provider outage) must raise instead - orchestration treats a
    raised exception, and only a raised exception, as
    ``ExplanationProviderStatus.LLM_UNAVAILABLE`` (no retry attempted);
    a returned ``narrative=None`` triggers exactly one retry instead.
    """

    def explain(self, request: ExplanationRequest) -> ExplanationLLMResponse: ...


__all__ = ["ExplanationLLMClient"]
