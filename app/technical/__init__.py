"""Stage 3A deterministic technical/market-structure analytics.

Converts normalized ``OHLCVCandle`` history into structured,
provider-agnostic, quality-tagged ``TechnicalFeatureSnapshot`` facts - never
a trading interpretation. No indicator math is delegated to an LLM.

Independent of ``app.flow``: this package never imports
``FlowFeatureSnapshot``, ``FlowAnalysisResult``, ``FlowSupervisorResult``,
``app.flow_analysts`` or ``app.flow_supervisor``, and never imports a
concrete provider (``app.market_data.providers.*``) - only the
provider-agnostic ``OHLCVCandle``/``Timeframe`` contracts.

Deliberately separate from the legacy, unused
``app.core.models.technical.TechnicalSnapshot`` placeholder, which this
package does not touch or supersede yet.

See ``app.technical.engine.TechnicalFeatureEngine`` for the composition
root.
"""
