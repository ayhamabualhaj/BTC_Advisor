# BTC Advisor — notes for Claude Code

A local Django tool that advises Ayham on daily Bitcoin trades. Three independent agents
(technical, derivatives, macro) each give a rule-based score (code) and an Opus judgment
score. The system only advises; Ayham places trades manually. Full plan:
`docs/project_plan.pdf`.

## Rules
- Never let a backtest see data from after the decision date.
- All math is done in code, never by the model.
- Every Opus call logs prompt version, tokens and cost.
- Changing a prompt creates a new PromptVersion, never edits the old one.
- No real trades are placed by the system.
- Ask before adding new libraries or paid services.

## Conventions
- No CrewAI or other agent framework: plain Python calls to the Anthropic API.
- Layering: View → Service → Repository/AI → Database. Models split into separate files
  under `apps/<app>/models/`.
- Each agent has its own folder `apps/agents/<name>/` with `prompt.md`, `rules.py`
  (rule-based score) and `agent.py` (the Opus call).
- Tests live in `tests/` at the root (`tests/test_<area>.py`).
- No nested project folders; every app has `migrations/__init__.py` and `admin.py`;
  `.env.example` matches the settings exactly.
- Short functions, clear names, a comment explaining *why* for anything non-obvious.
- After every step: `python manage.py check` and `python manage.py test`, then commit and
  push to GitHub (`origin main`).

## Layout
- `config/` — settings, urls.
- `apps/data/` — MarketData (long date/source/field/value table), collectors, indicators.
- `apps/agents/` — AgentRun, PromptVersion (text locked once saved), MemoryCase; per-agent rules and Opus calls.
- `apps/backtest/` — Decision, Outcome, BacktestRun, ManualTrade.
- `apps/dashboard/` — web pages (later).

## Data (step 3)
- `python manage.py collect_data [--start --end --source]` pulls and saves, then lists gaps.
- Dating rule: a MarketData date is the last UTC day by whose end the value was known
  (FRED daily +1 day, CPI dated by its release, funding by settlement). Keeps backtests honest.
- Sources: binance (OHLCV), bybit (funding_rate, open_interest, long_account_ratio),
  okx (liquidations), yahoo (dxy/nasdaq/sp500 closes; direct chart API, no yfinance),
  fred (needs FRED_API_KEY), farside ETF flows via `import_etf_flows <csv>`.
- Known limits: OKX keeps ~24h of liquidations, so there is no history and complete days
  need collection several times a day (step 13). Farside blocks scripts (Cloudflare), so
  ETF flows are imported from a CSV saved in the browser. Yahoo/FRED gaps on US holidays
  are expected.

## Indicators (step 4)
- `apps/data/indicators/` — pure math on lists (trend, momentum, levels, macro), no Django.
- `apps/data/services/indicator_service.py` — `technical_snapshot(date)`,
  `derivatives_snapshot(date)`, `macro_snapshot(date)`: reads only data dated <= date;
  a series older than 5 days counts as missing (None).
- Stand-ins for data with no free source: "cut expected" = 2-year yield 0.25 below fed
  funds; "CPI vs expectations" = latest monthly change vs the previous 3 months' average.

## Rule scores (step 5)
- `apps/agents/<agent>/rules.py` — `score(snapshot) -> RuleScore` (start 50, clamp 0-100;
  bullish >= 55, bearish <= 45). Weights and thresholds are named constants at the top of
  each file, to be tuned by the backtest. Missing data skips a criterion (listed in
  `skipped`), it never counts as bullish or bearish.
- `python manage.py score_rules [--date] [--save]` prints/stores rule-only AgentRuns.

## Progress
- [x] 1. Project setup
- [x] 2. Database models
- [x] 3. Data collectors
- [x] 4. Indicator calculations
- [x] 5. Rule-based scores
- [ ] 6. First backtest (rules only)
- [ ] 7. Opus agents
- [ ] 8. Opus backtest
- [ ] 9. Calibration check
- [ ] 10. Combining rule
- [ ] 11. REST API
- [ ] 12. Dashboard pages
- [ ] 13. Daily run
- [ ] 14. RAG memory
- [ ] 15. Optional extras

**Current step:** 6. First backtest (rules only)
