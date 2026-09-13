"""Uniform entry point the Stage 5A Market Evaluator implements.

Mirrors ``app.flow_supervisor.protocols.FlowSupervisorProtocol``/
``app.technical_supervisor.protocols.TechnicalSupervisorProtocol``/
``app.external_intelligence_supervisor.protocols.ExternalIntelligenceSupervisorProtocol``
one contour over: a stateless, synchronous, provider-agnostic aggregator
over already-produced Flow/Technical/External-Intelligence supervisor
results. Takes only the current pass's optional contour results, an
explicit ``MarketEvaluationContext``, an explicit ``evaluation_time``, and
the caller's own explicit ``expected_technical_symbol`` (the MT5/broker-
facing symbol Technical's result must match - a different provider identity
from ``context.symbol``, which stays Binance-only; see
``app.market_evaluation.evaluator``'s own docstring) - no history argument,
no storage, no network/provider methods, no configuration.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.core.models.base import Symbol, Timestamp
from app.core.models.external_intelligence_supervisor_result import ExternalIntelligenceSupervisorResult
from app.core.models.flow_supervisor_result import FlowSupervisorResult
from app.core.models.market_evaluation_context import MarketEvaluationContext
from app.core.models.market_evaluation_result import MarketEvaluationResult
from app.core.models.technical_supervisor_result import TechnicalSupervisorResult


@runtime_checkable
class MarketEvaluationProtocol(Protocol):
    """Stateless, synchronous, provider-agnostic Stage 5A aggregator."""

    def evaluate(
        self,
        *,
        flow: FlowSupervisorResult | None,
        technical: TechnicalSupervisorResult | None,
        external: ExternalIntelligenceSupervisorResult | None,
        context: MarketEvaluationContext,
        evaluation_time: Timestamp,
        expected_technical_symbol: Symbol,
    ) -> MarketEvaluationResult: ...


__all__ = ["MarketEvaluationProtocol"]
