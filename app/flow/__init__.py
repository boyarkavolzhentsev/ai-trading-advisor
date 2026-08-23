"""Deterministic crypto flow / futures microstructure analytics (Stage 2A).

Transforms already-validated Stage 0/1A/1B/1C market data (trades,
liquidations, order-book snapshots, open interest, funding) into structured,
quality-annotated ``FlowFeatureSnapshot`` facts - taker flow, liquidation
flow, order-book microstructure, open interest, funding and minimal price
context, each over a configurable set of ``AnalyticsWindow`` lookback
windows. Pure calculation only: no network I/O, no LLM calls, no trading
interpretation (no LONG/SHORT, no BUY/SELL, no risk/money management). See
``app.flow.engine.FlowFeatureEngine`` for the per-symbol orchestration entry
point and ``app.core.models.flow_feature_snapshot.FlowFeatureSnapshot`` for
the output contract.
"""
