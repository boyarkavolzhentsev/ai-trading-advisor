"""Deterministic Crypto Flow Supervisor (Stage 2C).

Aggregates already-produced Stage 2B ``FlowAnalysisResult`` objects for one
snapshot into one ``FlowSupervisorResult``: which analysts participated,
which abstained, which are missing, what evidence quality/coverage resulted,
and whether the one genuinely cross-domain-comparable signal (price/flow
relationship agreement, via ``PriceFlowRelationshipAnalyst``'s own
observations) agrees. Pure aggregation only: no re-derivation of Stage 2A/2B
facts, no analyst voting or weighting, no magnitude thresholds, no LLM
calls, and no trading interpretation (no LONG/SHORT, no BUY/SELL, no
confidence score, no risk/money management - that is a future Judge's job).
See ``app.flow_supervisor.protocols.FlowSupervisorProtocol`` for the entry
point and ``app.flow_supervisor.supervisor.FlowSupervisor`` for the
implementation.
"""
