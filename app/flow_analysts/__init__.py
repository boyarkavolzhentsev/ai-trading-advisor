"""Specialized deterministic crypto flow analysts (Stage 2B).

Interprets already-computed Stage 2A ``FlowFeatureSnapshot`` facts into
structured, evidence-backed ``FlowAnalysisResult`` observations - one narrow
specialist per Stage 2A domain, plus one relationship analyst. Pure
classification only: no raw-event aggregation (that stays in ``app.flow``),
no magnitude thresholds, no abnormality detection, no LLM calls, and no
trading interpretation (no LONG/SHORT, no BUY/SELL, no risk/money
management, no cross-analyst aggregation - that is a future Stage 2C Flow
Supervisor's job). See ``app.flow_analysts.protocols.FlowAnalyst`` for the
uniform entry point every analyst implements.
"""
