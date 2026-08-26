"""Deterministic Technical Supervisor (Stage 3C).

Aggregates already-produced Stage 3B ``TechnicalAnalysisResult`` objects for
one evaluation into one ``TechnicalSupervisorResult``: which
``(analyst_type, timeframe)`` cells participated, which abstained, which are
missing, what evidence quality/coverage resulted, and whether genuinely
comparable technical dimensions agree across timeframes. Pure aggregation
only: no re-derivation of Stage 3A/3B facts, no analyst or timeframe voting
or weighting, no magnitude thresholds, no LLM calls, and no trading
interpretation (no LONG/SHORT, no BUY/SELL, no confidence score, no risk/
money management - that is a future Judge's job). See
``app.technical_supervisor.protocols.TechnicalSupervisorProtocol`` for the
entry point and ``app.technical_supervisor.supervisor.TechnicalSupervisor``
for the implementation.

Independent of ``app.flow``/``app.flow_analysts``/``app.flow_supervisor``:
this package never imports those modules or their models, and never imports
a concrete provider (``app.market_data.providers.*``) - only the
provider-agnostic Stage 3B contracts.
"""

from __future__ import annotations
