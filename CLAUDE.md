# BTC Advisor — notes for Claude Code

A local Django tool that advises Ayham on daily Bitcoin trades. Three domains (technical,
derivatives, macro) each have three independent agents: rules (code), ML (logistic
regression, walk-forward) and Opus 5.5 (judgment). The system only advises; Ayham places trades manually. Full plan:
`docs/project_plan.pdf`.

## Rules
- Never let a backtest see data from after the decision date.
- All math is done in code, never by the model.
- Every Opus call logs prompt version, tokens and cost.
- Changing a prompt creates a new PromptVersion, never edits the old one.
- No real trades are placed by the system.
- Ask before adding new libraries or paid services.

## Conventions
- CrewAI Flows orchestrate the agents (plain Python steps, no CrewAI LLM agents). Opus is
  called only through `ai/opus_client.py`, so every call keeps its cost logging.
- Python 3.13 (CrewAI does not support 3.14 yet).
- Layering: View → Service → Repository/AI → Database. Models split into separate files
  under `apps/<app>/models/`.
- The AI lives in the top-level `ai/` package, outside `apps/`. Each domain has its own
  folder `ai/<domain>/` with `inputs.py` (setup as relative numbers), `rules.py`, `ml.py`,
  `opus.py` and `prompt.md`. Nothing in `ai/` touches the database (see AI layer below).
- Tests live in `tests/` at the root (`tests/test_<area>.py`).
- No nested project folders; every app has `migrations/__init__.py` and `admin.py`;
  `.env.example` matches the settings exactly.
- Short functions, clear names, a comment explaining *why* for anything non-obvious.
- After every step: `python manage.py check` and `python manage.py test`, then commit and
  push to GitHub (`origin main`).

## Layout
- `config/` — settings, urls.
- `apps/data/` — MarketData (long date/source/field/value table), collectors, indicators.
- `ai/` — the agents and the CrewAI Flow (no Django models, no database access).
- `apps/agents/` — AgentRun (rule_score, ml_score, opus_score), PromptVersion (text locked
  once saved), MemoryCase; services that build Briefs, run the Flow and save the runs.
- `apps/backtest/` — Decision, Outcome, BacktestRun, ManualTrade.
- `apps/dashboard/` — web pages (later).

## Database
- PostgreSQL (settings from DB_* in .env). `bash scripts/setup_postgres.sh` creates or
  repairs the role (with CREATEDB, needed by the test runner) and the database.

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
- `ai/<domain>/rules.py` — `score(snapshot) -> RuleScore` (start 50, clamp 0-100;
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
- `ai/<domain>/prompt.md` + shared `ai/output_instructions.md` = the system prompt.
  `apps/agents/services/prompt_service.py` makes a new PromptVersion whenever that text changes.
- `ai/<domain>/inputs.py` — `model_input(snapshot)`: relative numbers only (no
  absolute prices, levels or dates, so the asset and the year stay hidden). ML and Opus
  both use it.
- `ai/opus_client.py` — the only Anthropic API call: structured JSON output,
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

## Combining rule: the vote (replaces step 10's thresholds)
- `apps/backtest/decision_rule.py`: each voting agent says Buy (>= 55), Sell (<= 45) or Hold;
  Buy when Buy votes lead Sell votes by `min_net_votes`, Sell when the reverse.
- `python manage.py choose_combining_rule` (free): candidates rules / rules + ML, lead 1-3,
  chosen on 2019-2024 only (highest 7-day hit rate with >= 100 calls), then tested once on
  2025 onward. Saved as BacktestRun "combining_rule" (test-period numbers in the fields,
  tuning in settings). Chosen (Oct 2026): rules + ML, lead 2 -> 55.2% on 2019-24,
  62.9% on 2025-26 (+99.5% on buy days vs -14.5% buy-and-hold). The rules were tuned on
  2025-Sep 2026, so only Oct 2026 on is clean for everything.
- `decision_service.make_decision(date)` applies `combining_service.current_rule()` (default
  rules, lead 1) to the day's live AgentRuns; the Decision stores the rule and net votes.
- Long-only: in 2019-24 every vote strategy trailed buy-and-hold by far (it sits out rallies)
  but cut the worst drop; it beat holding in falling markets.

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

## Signals pages (after step 14)
- `/signals/?month=YYYY-MM&horizon=1|3|7`: one month from 2019 on, a Rules, ML and Opus
  column per domain plus the vote. Each call shows its confidence (Buy at 70 = 70% sure it
  rises, Sell at 30 = 70% sure it falls) and its result from its own side ("won +3.1%",
  "lost -2.0%"). `/signals/overview/`: hit rate per month and per period (2019-24, Jan
  2025-Sep 2026, Oct 2026 on) with which part was chosen where, and the "always up" base rate.
- Filters (agents, kind, days with a call / right / wrong) are client-side in
  `static/js/signals.js`, remembered in localStorage.
- Scores come from `apps/backtest/services/score_store.py`: DailyScore rows (rule + ML per
  day and agent) tagged with a hash of the agent code; changing rules / ML / inputs /
  indicators re-scores. The last 14 days are never stored. `python manage.py build_scores`
  fills it (~2 minutes from 2019); pages fill missing days themselves.

## Daily run (step 13)
- `python manage.py daily_run [--date] [--rules-only] [--force] [--no-collect]`: collects the
  last 10 days, runs the agents for yesterday UTC (Opus if ANTHROPIC_API_KEY is set, else
  rules and ML only), saves the Decision, updates Outcomes (prices after 1/3/7 days, correct per
  agent). Refuses a date that already ran unless --force, so retries never pay twice.
- Scheduling is the user's crontab (see README): daily_run at 00:15 UTC, plus
  `collect_data --source okx` every 4 hours for liquidations.

## RAG memory (step 14)
- `apps/agents/services/memory_service.py` + `ai/similarity.py`: a MemoryCase per agent and day = the agent's model input (as
  setup_summary JSON) + its 7-day return. The setup's own numbers are the embedding
  (standardized distance, missing features count as 2 std apart); no embedding service.
- Retrieval only uses cases dated <= decision date - 7 days (outcome known). Opus gets the
  5 closest as `similar_past_setups` (no dates). `build_memory` (free); daily_run adds new cases.

## Rule search (after step 14)
- All three rule sets were chosen by a search on Jan 2025 - Sep 23 2026 (no 7-day outcome
  reaches October), October held out. A rule set was kept only if its Buy (>= 55) / Sell
  (<= 45) calls were right >= 60% over 7 days on the whole period and ~55%+ in 2025 and
  2026 separately. Each rule is a full call (10 points); opposite rules cancel to Hold.
- Tuning hit rates when chosen (data from Jan 2025, so no 200-day average until Jul 2025):
  technical 63.5%, derivatives 60.1% (fragile to the funding thresholds), macro 63.1%.
  With the 2017+ history the same period gives 56.5% / 59.3% / 63.3% (technical's early-2025
  days now have a 200-day average). Never tuned on 2019-2024, a true holdout:
  55.0% / 47.8% / 53.1%. October, applied once: 82%, 82%, 80%, but every agent said
  Sell nearly every day and October fell, so it is one bearish call, not 17 wins.
- The rules lean bearish (technical sells unless the long trend is deeply down; macro sells
  on any CPI print not cooler than trend). Expect them to be wrong in a strong rally.
- Earlier reworks (mean reversion for technical, dropping OI/crowd rules for derivatives)
  are replaced. The edited technical and derivatives prompt.md files still describe those
  findings and are not saved as a version yet: the next Opus run makes them v3. The saved
  Opus backtest runs used v2 (the text before those edits).
- choose_combining_rule now stores the default rule when none qualifies, so an older
  choice made on other scores does not stay in force.

## AI layer and Flow (after step 14)
- `ai/flow.py` — a CrewAI Flow (`AdvisorFlow`): the rule, ML and Opus agents of every domain
  start together and never see each other's results; the last step returns one Verdict
  per domain. No CrewAI LLM agents: Opus goes through `ai/opus_client.py` only.
- CrewAI runs flow steps on a worker thread, where Django's database connection (and a
  test's transaction) is not available. So `apps/agents/services/agent_service.py` builds
  a `Brief` per domain (snapshot, setup, ML training cases, similar cases, prompt text)
  before the Flow and saves the AgentRuns after it. Keep the Flow steps database-free.
- `agent_service.run_agents(date, agents, use_opus, client, is_backtest)` is the one entry
  point (daily_run, run_agents, backtest_opus). Telemetry: settings.py turns CrewAI's
  anonymous telemetry, tracing and version check off before crewai is imported.

## ML agents (after step 14)
- `ai/ml.py`: logistic regression (scikit-learn) on the domain's setup numbers (the same
  `model_input` Opus sees, encoded by `ai/similarity.py`), score = chance (0-100) that the
  price is higher in 7 days. Retrained for every day on MemoryCases dated <= day - 7
  (walk-forward); fewer than 120 cases -> no score. Changing `model_input` needs `build_memory`.
- History: data since Aug 2017 (Binance, Yahoo, FRED) and Aug 2020 (Bybit) is stored;
  memory has ~3,350 days per domain. Days with fewer than 3 numbers are not trained on.
- With 2025-26 data only, walk-forward ML was 41-48% for technical and derivatives (what
  one period taught reversed in the next). With the 2017+ history it is ~47-56% per period
  (2019-22, 2023-24, 2025, 2026) and Brier ~0.25: no longer confidently wrong, but no
  stable edge in any setting (C 0.003-0.3; 1-year, 2-year, full windows). Kept C = 0.003
  on the full history (best Brier, stays near 50). A third opinion, not yet useful.
- Free everywhere: `backtest_rules --scores ml`, `calibration --scores ml`,
  `choose_combining_rule --scores ml`.

## Progress
- [x] 1. Project setup
- [x] 2. Database models
- [x] 3. Data collectors
- [x] 4. Indicator calculations
- [x] 5. Rule-based scores
- [x] 6. First backtest (rules only)
- [x] 7. Opus agents
- [x] 8. Opus backtest (run on Jul 1-20 and Oct 4-13, all agents)
- [x] 9. Calibration check
- [x] 10. Combining rule (rules-tuned; redo with --scores opus after the Opus backtest)
- [x] 11. REST API
- [x] 12. Dashboard pages
- [x] 13. Daily run
- [x] 14. RAG memory
- [ ] 15. Optional extras (not planned for now)

**Current step:** done through 14, rule search, Signals page, `ai/` package with rules / ML / Opus agents per domain run by a CrewAI Flow. Pending for the user: ETF CSV, crontab; optionally rerun the technical and derivatives Opus backtests, which would create prompt v3 (paid, ~$0.45 each).
