# ai-trading-advisor

Hierarchical multi-agent trading **advisory** system: market analysis, risk
management, MT5 tracking and performance evaluation.

The system produces recommendations for a human trader. It does not place
orders.

## Current development stage

**Stage 0 — project skeleton and typed domain contracts.**

What exists today:

- package skeleton for every future component area
- strongly typed enums (`app/core/enums`)
- Pydantic v2 domain contracts (`app/core/models`)
- trading cycle configuration contract (`app/core/config`)
- pytest suite covering the validation rules of those contracts

What deliberately does **not** exist yet:

- market data fetching, indicators, strategies
- exchange APIs, broker APIs, MT5 integration
- LLM agents, supervisors, orchestration
- databases, HTTP API, lot sizing, performance calculations

No fake or sample market data is shipped with the project.

## Architecture principles

| Role | Responsibility |
| --- | --- |
| Fetcher | gets external data |
| Calculator | deterministic calculations |
| Validator | validates data |
| LLM agent | interprets information |
| Supervisor | coordinates specialized components |
| Decision component | makes decisions |

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
(technical, flow, context, regime, strategy routing, risk, portfolio,
diversification, money management, target/session, decision, judge, policy gate,
execution quality, position management, statistics, post-trade review,
evaluation).

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

## Project layout

```
app/
  core/          enums, domain models, configuration contracts
  market_data/   fetchers and data validators
  markets/       us, eu, fx, crypto, metals, energies
  technical/     flow/  context/  regime/  strategies/
  risk/          money_management/  diversification/
  decision/      judge/  execution/
  mt5/           statistics/  evaluation/  orchestration/
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
