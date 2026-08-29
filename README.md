# ai-trading-advisor

Hierarchical multi-agent trading **advisory** system: market analysis, risk
management, MT5 tracking and performance evaluation.

The system produces recommendations for a human trader. It does not place
orders.

## Current development stage

**Stage 6A — Strategy Router.** Implemented and tested locally; not yet
committed/pushed.

| Stage | Component | Status |
| --- | --- | --- |
| 0 | Foundational domain contracts (enums, Pydantic models, config) | Done |
| 1 | Market data / infrastructure (Binance provider, realtime streaming) | Done |
| 2 | Flow contour (feature engine → analysts → supervisor) | Done |
| 3 | Technical contour (feature engine → analysts → supervisor) | Done |
| 4 | External Intelligence contour (macro/rates/news/on-chain → analysts → supervisor) | Done |
| 5 | Market Evaluation Layer (structural aggregation across Flow/Technical/External Intelligence) | Done |
| 6 | **Decision Layer** | In progress |
| 6A | — Strategy Router (structural strategy eligibility) | Implemented locally, tests green, not yet committed/pushed |
| 6B | — Judge (strategy-specific semantic interpretation, directional reconciliation) | Not implemented — design begins after 6A is closed |
| 6C | — Policy / Safety Gate (deterministic system policy over Judge output) | Not implemented — design begins after 6B |
| 7 | Money / Risk Management | Not started |
| 8 | Portfolio / Diversification | Not started |
| 9 | Statistics / Session Management | Not started |
| 10 | MT5 Tracking / Integration (read/tracking only, no order execution) | Not started |
| — | Delivery/integration: deterministic output presentation, an LLM explanation layer, API/Telegram delivery, final polish & testing | Not started, not yet numbered |

A possible semantic-reconciliation sub-stage (previously tracked under the
working name "Stage 5B") was evaluated and explicitly **skipped**:
cross-contour semantic reconciliation is deferred to strategy-specific
Decision-layer logic (Judge, Stage 6B) rather than to a generic
pre-Decision bridge stage.

What exists today:

- package skeleton for every future component area
- strongly typed enums (`app/core/enums`) and Pydantic v2 domain contracts
  (`app/core/models`)
- trading cycle configuration contract (`app/core/config`)
- provider-agnostic market data layer with a Binance adapter
  (`app/market_data`), including realtime streaming
- deterministic Flow, Technical and External Intelligence contours: feature
  engines, specialized analysts, and their supervisors (Stages 2-4)
- the deterministic Market Evaluation Layer (`app/market_evaluation`,
  Stage 5): structural aggregation of Flow/Technical/External Intelligence
  supervisor results - participation, quality, External Intelligence scope
  alignment, and traceability, with zero semantic reconciliation
- the deterministic Strategy Router (`app/strategies`, Stage 6A): structural
  strategy-family eligibility
- a pytest suite covering every contract and component above

What deliberately does **not** exist yet:

- Judge, Policy/Safety Gate, or any directional/semantic trade
  interpretation (Stage 6B/6C)
- Risk, Money Management, Portfolio/Diversification, Statistics, or MT5
  integration (Stages 7-10)
- broker order placement, modification, or cancellation of any kind
- LLM agents, an explanation layer, or any API/Telegram delivery surface
- databases, HTTP API

No fake or sample market data is shipped with the project.

## Market data (Stage 1A)

- **Binance is the first market data provider.** Binance Spot only.
- **The core stays provider-agnostic.** Application code depends on the
  `MarketDataProvider` protocol (`app/market_data/protocols.py`) and on the
  domain models, never on Binance. Adding a second venue means adding a
  subpackage under `app/market_data/providers`, nothing else.
- **Public REST market data only** — ticker price, book ticker, klines and
  exchange info.
- **No API key is required.** Nothing is signed and no private endpoint is
  called.
- **Real-time WebSocket streaming is implemented** (`app/market_data/realtime`,
  `app/market_data/providers/binance/futures/realtime`) alongside the
  original request/response snapshot reads.
- **Futures data is implemented**: funding rates, open interest, liquidations
  and order-book depth are all available via the Binance Futures provider
  (`app/market_data/providers/binance/futures`) and feed the Flow contour
  (Stage 2).
- Adapters do no business logic: no indicators, no direction inference, no
  sizing.

Provider contract:

| Method | Returns |
| --- | --- |
| `get_current_price(symbol)` | `PriceQuote` |
| `get_bid_ask(symbol)` | `BidAskQuote` |
| `get_ohlcv(symbol, timeframe, limit)` | `list[OHLCVCandle]` |
| `get_instrument_metadata(symbol)` | `InstrumentMetadata` |

Request path: **client** (HTTP only) → **mapper** (normalization) →
**`DataQualityValidator`** (verdict) → **domain models**.

Symbols exercised in this stage: `BTCUSDT`, `ETHUSDT`, `XRPUSDT`.
Timeframes mapped to Binance intervals:

| Internal | Binance |
| --- | --- |
| `M5` | `5m` |
| `M15` | `15m` |
| `H1` | `1h` |
| `H4` | `4h` |
| `D1` | `1d` |

Any other timeframe raises `UnsupportedTimeframeError` before a request is
made. Every failure that leaves the provider is a `MarketDataError` subclass
(`ProviderUnavailableError`, `InvalidProviderResponseError`,
`UnsupportedTimeframeError`, `UnknownSymbolError`); `httpx` exceptions never
escape the client.

`DataQualityValidator` is deterministic and never repairs data. It detects
empty results, unordered candles, duplicate timestamps, a stale latest candle,
a crossed or negative bid/ask, and a response describing the wrong symbol. The
Binance adapter aborts on an invalid verdict and logs a warning for data that
is merely stale.

Optional live check (needs internet, not part of `pytest`):

```bash
python scripts/check_binance_market_data.py
python scripts/check_binance_market_data.py --symbol ETHUSDT --candles 3
```

## Flow analysts (Stage 2B)

`app/flow_analysts` interprets a Stage 2A `FlowFeatureSnapshot`
(`app.core.models.flow_feature_snapshot`) into structured, evidence-backed
`FlowAnalysisResult` facts (`app.core.models.flow_analysis_result`) - one
narrow specialist per Stage 2A domain, plus one relationship analyst:

| Analyst | Interprets |
| --- | --- |
| `TakerFlowAnalyst` | `taker_flow` |
| `LiquidationAnalyst` | `liquidation` |
| `OrderBookLiquidityAnalyst` | `order_book` |
| `OpenInterestAnalyst` | `open_interest` |
| `FundingAnalyst` | `funding` |
| `PriceFlowRelationshipAnalyst` | `cross_features`, plus a narrow read of `price_context`/`taker_flow`/`open_interest`/`liquidation` to describe price-vs-flow relationships |

Every analyst implements the uniform `app.flow_analysts.protocols.FlowAnalyst`
protocol (`analyze(snapshot) -> FlowAnalysisResult`): synchronous, stateless,
provider-agnostic, independently callable, no network I/O, no shared mutable
state, and no dependency on another analyst.

Analysts classify only **sign, presence and structural window/band
comparisons** already computed by Stage 2A - no magnitude thresholds, no
"strong"/"unusual"/"extreme" labels, no abnormality detection (that needs a
reference distribution and is deferred to a later calibration stage). Every
`FlowAnalysisObservation` cites at least one `FlowEvidence` entry
(`app.core.models.flow_evidence`); there is no free-text summary field.
`FeatureQuality` (`VALID`/`PARTIAL`/`STALE`/`UNAVAILABLE`) is reused as-is
from Stage 2A via `app.flow.quality.worse_of` - Stage 2B never invents a
second severity system. An analyst **abstains** (`AnalystOutcome.ABSTAINED`,
with explicit `abstention_reasons`) when no meaningful observation can be
produced, rather than fabricating a neutral reading.

Stage 2B v1 reasons only across the windows already contained in **one**
snapshot - no cross-snapshot history, no calibrated thresholds, and no
cross-analyst aggregation (that is Stage 2C Flow Supervisor's job).
Analysts never emit a trading recommendation: no `LONG`/`SHORT`, no
`BUY`/`SELL`, no entry/stop-loss/take-profit/position-size/confidence field.
Directional interpretation is deferred to the Decision Layer's Judge
(Stage 6B, see below) once it exists; the pre-Stage-2B
`app.core.models.assessment.AgentAssessment`/`TradeDirection` contracts are
legacy, unused by any deterministic contour or by the Decision Layer, and are
untouched by this or any later stage.

## Market Evaluation (Stage 5)

`app/market_evaluation` deterministically aggregates one pass's already-
produced Flow (`FlowSupervisorResult`), Technical (`TechnicalSupervisorResult`)
and External Intelligence (`ExternalIntelligenceSupervisorResult`) supervisor
results, for one explicit `MarketEvaluationContext`
(`app.core.models.market_evaluation_context`), into one
`MarketEvaluationResult` (`app.core.models.market_evaluation_result`).

It reports, per contour: participation (`MarketEvaluationContourStatus`:
`MISSING`/`INSUFFICIENT_EVIDENCE`/`PARTIAL`/`ANALYZED`), quality
(`FeatureQuality`), and - for External Intelligence only, whose native scopes
carry no shared instrument anchor - structural scope alignment against the
caller's explicit context (exact identity matching on `symbol`,
`base_asset`+`network`, or `currency`; never fuzzy matching or inference).

Market Evaluation performs **zero semantic cross-contour comparison**: no
agreement/contradiction/coherence/confluence engine, no direction, no score,
no confidence, no trading recommendation of any kind - it can structurally
never carry one. A previously-considered semantic-reconciliation sub-stage
(the working name "Stage 5B") was evaluated and skipped in favor of doing
that work, narrowly and strategy-by-strategy, inside the Decision Layer's
Judge (Stage 6B) once it exists.

## Decision Layer (Stage 6)

The Decision Layer consumes exactly one Stage 5 `MarketEvaluationResult` and
is decomposed into three narrow, non-overlapping sub-stages. No sub-stage
places, modifies, or cancels an order - V1 stays advisory-only end to end.

### Strategy Router (Stage 6A) — implemented

`app/strategies` answers one structural question per strategy family: "does
this family have enough structurally-present, non-`UNAVAILABLE` evidence for
Judge to be allowed to interpret it?" It never decides whether a strategy is
currently good, and it never inspects semantic dimension/value content -
only `MarketEvaluationResult`'s own contour status/quality/external-alignment
fields (`app.core.enums.market_evaluation`, `app.core.enums.quality`).

V1 strategy families (`app.core.enums.strategy_router.StrategyFamily`):
`TREND_FOLLOWING`, `MEAN_REVERSION`, `BREAKOUT`, `EVENT_DRIVEN`.
`TREND_FOLLOWING` and `MEAN_REVERSION` intentionally share an identical
structural eligibility rule in V1 - Stage 6A has no structural fact that can
distinguish a trending market from a ranging one; that distinction belongs to
Stage 6B Judge.

Router never ranks families, never selects a preferred strategy, never
computes confidence/score/strength/weight, never emits `LONG`/`SHORT`, and
never executes anything. Multiple families may be eligible simultaneously;
`StrategyRouterResult.eligible_families` lists all of them with no implied
order of preference.

Status: implemented and tested locally (`app/strategies/router.py`,
`app/strategies/protocols.py`, `app.core.enums.strategy_router`,
`app.core.models.strategy_router_result`); not yet committed/pushed.

### Judge (Stage 6B) — not implemented

Judge will be the first Decision-layer component allowed to perform explicit,
strategy-specific semantic interpretation of Flow/Technical/External
Intelligence dimension content, reconciling it into a deterministic verdict
per eligible strategy family and, only where the evidence genuinely agrees, a
directional candidate. Its exact contracts and per-family rules are not
finalized yet and are not documented here.

### Policy / Safety Gate (Stage 6C) — not implemented

Policy/Safety Gate will apply deterministic system-policy constraints over
Judge's output before Risk/Portfolio review - for example whether stale
evidence is acceptable, and enforcing the advisory-only boundary - never
capital sizing or portfolio exposure math, which stay in later stages. Its
exact contract is not finalized yet and is not documented here.

## Architecture principles

| Role | Responsibility |
| --- | --- |
| Fetcher | gets external data |
| Calculator | deterministic calculations |
| Validator | validates data |
| LLM agent | interprets information |
| Supervisor | coordinates specialized components |
| Decision component | makes decisions |

The Decision Layer (Stage 6, above) splits the single "Decision component"
role into three narrower stages - Strategy Router (structural eligibility),
Judge (semantic interpretation), Policy/Safety Gate (system policy) - each
documented under Decision Layer (Stage 6) above.

Rules that shape every contract in this repository:

- **Deterministic financial arithmetic is never delegated to an LLM.** Prices,
  risk, position size and P&L are computed by calculators; LLM agents only
  interpret and explain.
- Money-like values use `Decimal`, never `float`. Dimensionless scores and
  ratios use `float`.
- All timestamps are timezone-aware; naive datetimes are rejected so broker
  server time and local time cannot be silently mixed.
- Contracts are immutable value objects. The only mutable record is
  `PositionRecord`, which an external tracker updates over a trade's lifecycle.
- Risk and target parameters live in configuration models
  (`TradingCycleConfig`), never hard-coded in logic.
- Modules stay small, typed, testable and loosely coupled. `app/core` depends on
  nothing else in the app.

## Future market domains

- US markets
- EU markets
- FX
- Cryptocurrencies
- Metals
- Energies

Each domain gets its own market domain supervisor under `app/markets/<domain>`,
coordinated by a global orchestrator, alongside functional supervisors
(technical, flow, context, regime, the Decision Layer - strategy routing /
judge / policy gate (Stage 6), risk, portfolio, diversification, money
management, target/session, execution quality, position management,
statistics, post-trade review, evaluation).

## Signal execution window

A `LONG`/`SHORT` recommendation is only executable inside a fixed window:

```
valid_until = signal_time + SIGNAL_EXECUTION_WINDOW   # 5 minutes
```

`TradeSetup` and `PositionRecord` carry both timestamps and validate that
`valid_until` is after `signal_time`. Expiry timers are not implemented yet — a
recommendation that is never acted on is recorded as `NOT_FILLED` / `EXPIRED`.

## Risk and target envelope

`TradingCycleConfig` carries the configurable cycle envelope. Defaults are
examples only:

| Parameter | Default |
| --- | --- |
| `starting_equity` | 100 000 |
| `target_profit_percent` | 6.0 % |
| `daily_risk_limit_percent` | 1.5 % |
| `max_cycle_drawdown_percent` | 7.5 % |
| `cycle_days` | 14 |

Planned rule (not implemented): at every broker/server trading-day rollover the
daily risk budget is recalculated from **current account equity** — e.g. equity
98 500 at 1.5 % gives a budget of 1 477.50. Remaining risk-to-stop of positions
carried into the new day consumes part of that budget. `MoneyManagementDecision`
already models equity, daily budget, used open risk and available new risk so
this rule can be implemented without a contract change.

Session state is expressed by `TradingSessionStatus`: `ACTIVE`,
`REDUCED_RISK`, `CAPITAL_PRESERVATION`, `TARGET_REACHED`,
`LOSS_LIMIT_REACHED`, `LOCKED`.

## Scope of V1

- **V1 is advisory only. Execution is manual** — the trader decides and places
  every order.
- **MT5 will initially be read/tracking only**: account state, instrument
  specifications and position tracking.
- **Automated trading is explicitly NOT part of V1.** No order placement, no
  modification, no closing of positions by the system.
- Once the full Decision → Risk → Portfolio chain exists, a final `LONG`/
  `SHORT` recommendation is intended for **manual** placement by the trader
  in MT5, within the defined execution/validity window - never placed by the
  system itself.

## Project layout

```
app/
  core/                              enums, domain models, configuration contracts
  market_data/                       provider protocol, quality validator, provenance,
                                      realtime streaming (Stage 1)
    providers/binance/               public Spot/Futures REST client + realtime, mapper, adapter
  flow/  flow_analysts/  flow_supervisor/
                                      Stage 2A-2C: flow feature engine, specialized
                                      analysts, contour supervisor
  technical/  technical_analysts/  technical_supervisor/
                                      Stage 3A-3C: technical feature engine, specialized
                                      analysts, contour supervisor
  macro/  rates/  news/  news_intel/  onchain/
                                      Stage 4A-4E: external-intelligence foundations
  external_intelligence_analysts/  external_intelligence_supervisor/
                                      Stage 4F-4G: specialized analysts, contour supervisor
  market_evaluation/                 Stage 5: deterministic cross-contour aggregation
  strategies/                        Stage 6A: Strategy Router (implemented)
  judge/                             Stage 6B: Judge (not implemented)
  decision/                          Stage 6C: Policy / Safety Gate (not implemented)
  risk/  money_management/  diversification/
                                      Stage 7-8 (not implemented)
  statistics/                        Stage 9 (not implemented)
  mt5/                               Stage 10: read/tracking integration (not implemented)
  markets/                           us, eu, fx, crypto, metals, energies market domains
  context/  regime/  execution/  orchestration/  evaluation/
                                      future supervisors/components (not implemented)
scripts/                             manual live checks (not part of the test suite)
tests/
```

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
pytest
```

Requires Python 3.11+ (`StrEnum`, `Self`).

## Disclaimer

This software produces informational analysis only. It is not investment
advice, and it carries no guarantee of profit. Trading involves substantial risk
of loss.
