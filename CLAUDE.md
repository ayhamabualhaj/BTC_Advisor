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

## Backtest (step 6)
- Daily strategy: a buy signal at the close of day D holds to the close of D+1;
  consecutive buy days are one trade. Test period starts 2026-07-01 (after Opus 5.5's
  training cutoff). `apps/backtest/metrics.py` is the pure math.
- `python manage.py backtest_rules [--start --end --threshold --agents-required --no-save]`
  saves one BacktestRun per agent plus "combined", each compared with buy-and-hold.

## Opus agents (step 7)
- `apps/agents/<agent>/prompt.md` + shared `apps/agents/output_instructions.md` = the system
  prompt. `apps/agents/ai/prompts.py` makes a new PromptVersion whenever that text changes.
- `apps/agents/<agent>/agent.py` — `model_input(snapshot)`: relative numbers only (no
  absolute prices, levels or dates, so the asset and the year stay hidden), and `run()`.
- `apps/agents/ai/opus_client.py` — the only Anthropic API call: structured JSON output,
  effort from AI_EFFORT, one retry on invalid output, tokens and cost on every call.
  Prices ($4 / $20 per M tokens for Opus 5.5) are constants there.
- Opus never sees the rule score or other agents' results. opus_score = confidence (0-100)
  that the price is higher in 7 days.
- `python manage.py run_agents [--date] [--agent]` (paid). Tests use `tests/fake_anthropic.py`.

## Opus backtest (step 8)
- `python manage.py backtest_opus --estimate` first (free), then
  `backtest_opus [--agent] [--max-cost 5]` (paid). Runs each agent alone, day by day, with
  only data up to that day; skips days already done for the current prompt version, so it
  resumes after a stop and never pays twice. Results saved as BacktestRuns named "opus:*".

## Calibration (step 9)
- `apps/backtest/calibration.py`: a score s = "s% chance the price is higher in 7 days";
  below 50 it is a down call with confidence 100-s; 50 is no call. Buckets 50s-90s with hit
  rate vs stated confidence, plus a Brier score (0.25 = always saying 50).
- `python manage.py calibration --scores rules|opus [--horizon 7]` (opus reads saved
  backtest runs, never calls the API). Saved as BacktestRuns named "<type>:<agent>:calibration".

## Combining rule (step 10)
- `python manage.py choose_combining_rule --scores rules|opus`: tries all three / any two
  agents >= 55..80, keeps the highest profit with at least 3 trades (ties: lower drawdown),
  shows first-half / second-half profit to expose overfitting. Saved as "<type>:combining_rule".
- `decision_service.make_decision(date)`: applies the latest chosen rule (Opus-tuned
  preferred, else rules-tuned, else 3 agents >= 60) to the day's live AgentRuns.
- With ~115 test days the chosen rule is fragile; re-run after the Opus backtest.

## REST API (step 11)
- Read-only, no login (local only). `apps/dashboard/`: views/api_views.py → services/
  report_service.py → repositories/report_repository.py. Endpoints under /api/:
  `decision/today/`, `agent-runs/?agent=&backtest=&date=`, `backtests/?name=`, `costs/`,
  `prompts/?agent=` (each version with runs, errors, cost, 7-day hit rate).

## Dashboard (step 12)
- `python manage.py runserver` then http://127.0.0.1:8000/ — Today, one page per agent
  (live/backtest toggle, score chart), Backtests (profit vs buy-and-hold, calibration,
  combining rule), Costs, Prompts. Views in `apps/dashboard/views/page_views.py` use the same
  report_service as the API. Templates in `templates/`, CSS tokens (light + dark) in
  `static/css/style.css`, Chart.js 4.4.1 from jsDelivr with helpers in `static/js/charts.js`.
- Combining-rule thresholds start at 55: a score of 50 means "no edge" and never buys.

## Daily run (step 13)
- `python manage.py daily_run [--date] [--rules-only] [--force] [--no-collect]`: collects the
  last 10 days, runs the agents for yesterday UTC (Opus if ANTHROPIC_API_KEY is set, else
  rules only), saves the Decision, updates Outcomes (prices after 1/3/7 days, correct per
  agent). Refuses a date that already ran unless --force, so retries never pay twice.
- Scheduling is the user's crontab (see README): daily_run at 00:15 UTC, plus
  `collect_data --source okx` every 4 hours for liquidations.

## Progress
- [x] 1. Project setup
- [x] 2. Database models
- [x] 3. Data collectors
- [x] 4. Indicator calculations
- [x] 5. Rule-based scores
- [x] 6. First backtest (rules only)
- [x] 7. Opus agents
- [x] 8. Opus backtest (code done; not yet run: needs ANTHROPIC_API_KEY)
- [x] 9. Calibration check
- [x] 10. Combining rule (rules-tuned; redo with --scores opus after the Opus backtest)
- [x] 11. REST API
- [x] 12. Dashboard pages
- [x] 13. Daily run
- [ ] 14. RAG memory
- [ ] 15. Optional extras

**Current step:** 14. RAG memory (pending: run the Opus backtest once ANTHROPIC_API_KEY is set)
