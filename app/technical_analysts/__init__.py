"""Specialized deterministic technical analysts (Stage 3B).

Interprets already-computed Stage 3A ``TechnicalFeatureSnapshot`` facts into
structured, evidence-backed ``TechnicalAnalysisResult`` observations - one
narrow specialist per Stage 3A feature block. Pure classification only: no
indicator recomputation (that stays in ``app.technical``), no magnitude
thresholds, no abnormality detection, no LLM calls, and no trading
interpretation (no LONG/SHORT, no BUY/SELL, no risk/money management, no
cross-analyst or cross-timeframe aggregation - that is a future Stage 3C
Technical Supervisor's job). See
``app.technical_analysts.protocols.TechnicalAnalyst`` for the uniform entry
point every analyst implements.

Independent of ``app.flow``/``app.flow_analysts``/``app.flow_supervisor``:
this package never imports those modules or their models, and never imports
a concrete provider (``app.market_data.providers.*``) - only the
provider-agnostic ``TechnicalFeatureSnapshot`` contract and Stage 3A's own
quality-verdict helpers.
"""
