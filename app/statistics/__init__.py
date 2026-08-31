"""Stage 9: Statistics / Session Management.

Two deterministic, decoupled concerns:

- ``app.statistics.aggregator.StatisticsAggregator`` - trade statistics
  aggregation producing ``PerformanceSnapshot`` from an explicit
  ``PositionRecord`` history. Reporting only.
- ``app.statistics.session.SessionGate`` - deterministic session-status
  derivation and global pass/block gating over one ``StrategyPortfolioResult``.

Neither influences the other: statistics never affect session eligibility.
"""
