# BTC Advisor — notes for Claude Code

A local Django tool that advises Ayham on daily Bitcoin trades. Three domains (technical,
derivatives, macro) each have three independent agents: rules (code), ML (walk-forward:
logistic regression, random forest for macro) and Opus 5.5 (judgment). A fourth domain,
financial stress, has only an ML agent (see "Financial stress domain"); a fifth, the risk-on
day, only a rules agent (see "Risk-on day domain"); a sixth, the dollar, only an ML agent that
votes only in the second strong signal (see "Strong signal with the dollar agent"). The system only advises; Ayham places trades manually. Full plan:
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
  (FRED daily +1 day, funding by settlement). Keeps backtests honest. CPI, core CPI and NFCI
  are revised after release, so they are stored as first published (ALFRED initial release),
  dated by the publication day; two published the same day -> the later one a day late.
  Each CPI print also stores the month it measures (`cpi_month`, YYYYMM, same day): October
  2025 was never published, so the prints are not consecutive months.
- Sources: binance (OHLCV), bybit (funding_rate, open_interest, long_account_ratio),
  okx (liquidations), yahoo (dxy/nasdaq/sp500 closes; direct chart API, no yfinance),
  fred (needs FRED_API_KEY), farside ETF flows via `import_etf_flows <csv>`.
- Known limits: OKX keeps ~24h of liquidations, so there is no history and complete days
  need collection several times a day (step 13). Farside blocks scripts (Cloudflare), so
  ETF flows are imported from the table copied in a browser, saved as
  `data/imports/etf_flows.txt` (git-ignored; imported Jan 2024 - Oct 2026, used only by the macro LLM input). Yahoo/FRED gaps on US holidays
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
  absolute prices, levels or dates, so the asset and the year stay hidden). Opus uses it;
  ML uses it for technical and derivatives (macro ML has its own features, see ML agents).
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

## Combining rule: the two-round vote, 3 of 5 (Oct 27 2026, the user's choice)
- Round 1 as below (Rules vote: technical, derivatives, macro rules; ML vote: macro ML only;
  LLM vote). Round 2 has five voters (`decision_rule.VOTERS_ROUND_2`): those three votes plus
  financial stress ML and the risk-on day rule, each voting on its own (`SOLO`, so stress no
  longer votes inside the ML vote). Buy or Sell when 3 of the 5 say it (`OVERALL_NEEDED`);
  no score or Hold counts as not agreeing. Stored as overall = "3 of 5"; older choices ignored.
- choose_combining_rule: group lead 1 again. 2019-24 (no LLM): 56.6% of 371 calls, +202%,
  worst drop 22% (old "all agree": 54.0% of 626, +149%, 34%). 2025 - Oct 25 2026 with Haiku:
  68.1% of 91 calls, +32.9%, drop 9.7% (hold -15.3%); old vote on the same days 78.9% of 57,
  +32.7%. More calls, lower hit rate, same profit from 2025; better on 2019-24.
- Today page: a "Who voted" table (`report_service.vote_breakdown`): each voter's call, the
  agents behind it with scores, and which are shown only (technical / derivatives ML).

## Combining rule: the earlier two-round vote ("all agree", replaced Oct 27 2026)
- `apps/backtest/decision_rule.py`: every agent says Buy (>= 55), Sell (<= 45) or Hold.
  Round 1: the rules agents of the 3 domains vote -> the Rules vote; likewise the ML vote
  and the Opus vote (Buy when Buy leads Sell by `group_lead`). Round 2, the overall vote:
  Buy or Sell only when every group vote agrees. A group with no scores (Opus before
  mid-2026) sits out, but at least 2 groups must have voted.
- `python manage.py choose_combining_rule` (free): group lead 1-3, chosen on 2019-2024 only
  (highest 7-day hit rate with >= 100 calls), tested once on 2025 onward. Opus has no
  2019-24 scores, so the choice is made on Rules and ML agreeing; live, Opus must agree
  too (untested). Saved as BacktestRun "combining_rule" with overall = "all agree"; choices
  saved under older votes are ignored.
- Chosen (Oct 26 2026): group lead 1 (the only one with 100+ calls) -> 52.3% of 514 calls
  on 2019-24 (below "always up", 54%), 75.3% of 93 calls on 2025-26, +21.7% on 63 buy days
  vs -14.5% buy-and-hold. The rules were tuned on 2025-Sep 2026, which flatters 2025-26.
- With the Haiku v3 vote (AI_MODEL=claude-haiku-5-5; choose_combining_rule now passes the
  LLM scores, which only exist from 2025, so they never affect the choice): 72.1% of 61
  calls on 2025-26, +11.6%, vs 75.3% of 93 without it. Each group alone on 2025-26: Rules
  63.6% of 516 (tuned there), Haiku 58.4% of 332, ML 53.7% of 339; "always up" 51.8% /
  48.3%. Requiring the LLM to agree cuts calls and did not raise the hit rate.
- Replaced: one-round vote of rules + ML as 6 voters, lead 2 (53.7% -> 62.4%); round 2 by
  lead (group 3 / overall 1: 54.5% -> 61.7%).
- `decision_service.make_decision(date)` applies `combining_service.current_rule()` to the
  day's live AgentRuns; the Decision stores the rule, each group's call and round 2's net.
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
- Today's "What should I do today?" button (POST /advise/, `daily_run_service.advice()`): runs
  daily_run for yesterday UTC if it has not run (paid LLM calls, ~$0.002 with Haiku), else
  only reads the saved Decision; shows BUY / SELL / HOLD from the overall vote and who voted.
- One "Agents" menu link (/agents/ opens the first agent); each agent page has a tab per agent
  (keeps the live / backtest choice), so the top bar stays short as agents are added.
- Combining-rule thresholds start at 55: a score of 50 means "no edge" and never buys.

## Pages rework (Nov 11 2026)
- Fees: `metrics.FEE_PER_SIDE` = 0.1% each time the position changes (long to short pays
  twice; the last position is closed). The Profit page is after fees with "Before fees" beside
  it; buy-and-hold pays two fees. Saved BacktestRuns keep `profit_after_fees_pct` in settings
  (older runs show –; rerun `backtest_rules` / `choose_combining_rule`, free, to fill it).
- Strong signal: `decision_rule.STRONG_NEEDED` = 4 of the 5 voters (`strong_call`). Shown as
  a badge on Today, a "Strong (4 of 5)" column on Signals and a row on Profit; it changes no call.
- Today: stale notice when the decision is older than yesterday, Bitcoin close tile, a
  120-day price chart with the vote's Buy / Sell days (`report_service.price_chart`), the
  vote's track record since 2025 as trades (`track_record`: days in a row = one trade, judged
  on its first day after 7 days), agent cards showing only the kinds a domain has.
- Agent page: one run per day (`agent_history` keeps the run with an LLM score), a 7-day hit
  rate per period (`agent_record`), score chart on a 30-70 axis with the Buy 55 / Sell 45 lines.
- Display only, in `apps/dashboard/templatetags/dashboard_format.py`: `field_label` /
  `field_value` name and round the key_data fields (add a new field's name to `LABELS`),
  `ml_reason` rewrites the ML reason lines, `versioned_static` adds the file's modified time to
  CSS / JS links so the browser never shows a stale copy. Stored values are untouched.
- Dates read "10 Nov 2026" on every page (`config/formats/en/formats.py`, FORMAT_MODULE_PATH);
  charts show "10 Nov" (`dayLabel` in charts.js), are not animated, and a "Theme" button in the
  top bar switches Auto / Light / Dark (localStorage "theme"). The footer shows the last stored
  close (`context_processors.freshness`).
- `daily_run` after a pause collects from the last stored price and adds memory from the last
  case (`collect_start`, `memory_start`), so a gap of more than 10 days leaves no hole.

## Signals pages (after step 14)
- `/signals/?month=YYYY-MM&horizon=1|3|7`: one month from 2019 on, a Rules, ML and Opus
  column per domain, then the Rules, ML and Opus votes (round 1) and the Overall vote. Each call shows its confidence (Buy at 70 = 70% sure it
  rises, Sell at 30 = 70% sure it falls) and its result from its own side ("won +3.1%",
  "lost -2.0%"). `/signals/overview/`: hit rate per month and per period (2019-24, Jan
  2025-Sep 2026, Oct 2026 on) with which part was chosen where, and the "always up" base rate.
- Filters (agents, kind, days with a call / right / wrong) are client-side in
  `static/js/signals.js`, remembered in localStorage.
- Scores come from `apps/backtest/services/score_store.py`: DailyScore rows (rule + ML per
  day and agent) tagged with a hash of the agent code; changing rules / ML / inputs /
  indicators re-scores (`SOURCE_FILES`: only files that change rule/ML scores, so editing the
  Opus client, prompts or Flow keeps them). The last 14 days are never stored; they are kept
  in the process's memory for an hour, cleared by new data. `python manage.py build_scores`
  fills it (~6 minutes from 2019, free); run it after editing any SOURCE_FILES, or the pages
  rescore missing days themselves (slow: the overview then rescores every day since 2019).
- Speed: CrewAI (~3.5 s) and scikit-learn are imported only when agents run or a model is
  trained, so pages start fast. Stored months load in ~0.05 s, the current month ~2 s once
  per hour (recent days are scored live), the overview ~0.25 s.

## Profit page
- `/profit/?period=since-2025|2026|2025|90d|2019-2024|all` or `?start=&end=`, `&short=1`:
  each Signals column (11 agents, Rules / ML / LLM votes, overall vote) as a strategy: Buy =
  long close D to close D+1; Sell = flat, or short with `short`. `&days=3|7` holds each call that
  many days (a new Buy / Sell replaces it); `&between=hold` holds Bitcoin when no call runs (how
  to judge the Sell-only risk-on day: from 2025 +52.7% at 1 day, +77.9% at 3, +14.9% at 7, vs
  hold -15.3%; with "stay out" it never trades, 0%). Profit, vs holding, worst
  drop, trades, trades won, coverage, and one chart line per agent. `profit_service.py` builds
  it from score_store + LLM runs; math in `metrics.py` (positions 1 / 0 / -1). Filters and sort
  are client-side in `static/js/profit.js` (localStorage "profit-filters"). Free.

## Daily run (step 13)
- `python manage.py daily_run [--date] [--rules-only] [--force] [--no-collect]`: collects the
  last 10 days, runs the agents for yesterday UTC (Opus if ANTHROPIC_API_KEY is set, else
  rules and ML only), saves the Decision, updates Outcomes (prices after 1/3/7 days, correct per
  agent). Refuses a date that already ran unless --force, so retries never pay twice.
- It also runs days the agents missed in the last 14 (`daily_run_service.missed_days`: a BTC
  close but no LLM score from any run, or with no LLM no live run), oldest first, each with
  its Decision, so Signals and Profit have no holes. Never before the history began (a new
  install does not backfill) and never twice (a day with a backtest LLM score counts as done).
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
  are replaced. The saved Opus backtest runs used prompt v2; see "Prompts v3" below.
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
- `ai/ml.py`: the models; `ai/<domain>/ml.py`: `features(snapshot, setup)` (stored per day
  as `MemoryCase.ml_features`), `training_cutoff(date)` and `score(brief)`. score = chance
  (0-100) that the price is higher in 7 days; fewer than 120 cases -> no score. Changing
  features needs `build_memory`, then `build_scores`.
- Technical, derivatives: logistic regression (C = 0.003) on the Opus setup numbers,
  retrained every day on cases dated <= day - 7.
- Macro: random forest (300 trees, depth 6, leaves >= 50, missing-value flags) on 11 macro
  moves (dollar 2w/1m, Nasdaq vs 50-day / 5d / 20d, S&P 20d, Fed move, 2y - fed funds,
  2y 20-day change, CPI yoy, CPI surprise). Retrained monthly on cases dated <= month
  start - 8 days, cached in-process, so a backtest fits one forest per month.
- Model study (Oct 2026): 12 models per domain (logistic C 0.01-1, forests, extra trees,
  boosting, kNN, MLPs), train before 2025, choose on 2025, test once on 2026. Only macro
  held up: forest 59.4% on 2025 -> 60.7% on 2026. Technical forest 58.3% -> 45.1% and
  derivatives MLP 54.4% -> 41.4% failed, so they stay on the cautious logistic model.
  In the project (stored scores): macro ML 50.2% on 2019-24 (little history to learn from
  early), 56.0% on 2025, 59.3% on 2026.
- A rule search on 2017-2024 (tested on 2025) also failed: 66.7 / 65.7 / 61.4% when tuned,
  42 / 39 / 51% on 2025. The 2025-Sep 2026 rules were kept.
- History: data since Aug 2017 (Binance, Yahoo, FRED) and Aug 2020 (Bybit) is stored;
  memory has ~3,350 days per domain. Days with fewer than 3 numbers are not trained on.
- With 2025-26 data only, walk-forward ML was 41-48% for technical and derivatives (what
  one period taught reversed in the next). With the 2017+ history it is ~47-56% per period
  (2019-22, 2023-24, 2025, 2026) and Brier ~0.25: no longer confidently wrong, but no
  stable edge in any setting (C 0.003-0.3; 1-year, 2-year, full windows). Kept C = 0.003
  on the full history (best Brier, stays near 50).
- Free everywhere: `backtest_rules --scores ml`, `calibration --scores ml`,
  `choose_combining_rule --scores ml`.

## Prompts v3 (Oct 2026, saved as PromptVersion v3)
- The "what history showed" lessons are now measured on 2017-2024 only (2025 on is the
  test): a pattern is taught only if, against each block's own base rate (2017-19,
  2020-21, 2022, 2023-24), the share of up weeks after it moved the same way in every
  block with >= 30 such days, and by >= 4 points overall. Mixed ones are named as such.
- Technical: momentum continued, the opposite of v2's mean reversion: RSI > 70 +9 pts,
  30-day rally > 20% +7, 7-day rally > 10% +7, > 8% above the 20-day +7; > 20% below the
  200-day +6; within 3% under resistance -6. No edge: 50/200-day position and cross,
  MACD, RSI 30-70, sharp drops, near support.
- Derivatives (2020-24): OI 3-day < -10% +5, OI and price both down > 3% +8, 7-day
  funding negative +5, 30-day funding > 0.02% -6. No edge: OI up with price down, crowd vs
  90-day average, one day of high funding. Liquidations untested (no history).
- Macro: only a Fed hike in the last 60 days held (-5). CPI cooler than trend, dollar up
  > 2% in a month and a Nasdaq 5-day drop are mixed (flip by period). Everything else: no edge.
- Base rate stated (54% up after 7 days on 2017-24); 55+ / 45- are acted on as calls, so
  the model gives one only with a tested pattern, else 46-54; rarely beyond 35-65.
- `similar_past_days` (memory_service.similar_summary): instead of 5 raw cases, the 50
  closest past days summarized in code: share up after 7 days, median move, all-days share.
- Inputs: macro adds dollar 1-month, Nasdaq 5-day, S&P 20-day and 2-year 20-day changes and
  drops `cuts_expected`; derivatives adds 30-day funding (Opus only; `OPUS_ONLY` keeps the
  derivatives ML on the numbers it was tested with).
- Caveat: overlapping 7-day windows make the counts look bigger than they are (~1/7 as many
  independent weeks); these are tendencies, not edges proven at a high bar. Note the rules
  (tuned on 2025-Sep 2026) lean bearish where these 2017-24 patterns lean bullish: the
  test period may simply be a different market.
- `python manage.py compare_prompts [--model] [--old 2 --new 3] [--start --end] [--estimate]
  [--max-cost 3] [--report]` (paid): the same model asks every day with both versions, v2
  with its own old input (`ai/inputs_v2.py`, 5 raw similar setups), v3 with the new one;
  8 calls in parallel, resumable. Runs are saved with model = the asked model, so Opus pages
  never show them.
- Result, Haiku 5.5, Jan 2025 - Oct 17 2026 (655 days x 3 agents x 2 versions, $2.05),
  7-day horizon: v3 56.8% of 454 calls vs v2 48.5% of 852 ("always up": 51.8% in 2025,
  48.3% in 2026). Per year v3 58.9% / 55.3%, v2 48.3% / 48.8%; every agent better (technical
  56.9 vs 44.8, derivatives 55.6 vs 49.6, macro 57.2 vs 50.3). Brier 0.2502 vs 0.2537: v3
  stops being worse than "always 50" but is barely better (macro 0.2487). v3 holds far more
  (70-90% of days) and almost never sells on derivatives. At 1 day v3 is no better (48.5%);
  it was written for 7 days. Overlapping weeks: ~1/7 as many independent calls.

## Agents tested and not added (Oct 26 2026)
- Bar fixed before each test; scripts were throwaway, nothing is in the code.
- Market regime (rules only; bull/bear/sideways from 200-day average, its slope, 50/200
  cross), used as a switch on the overall vote (bull: hold unless Sell; bear: vote only or
  stay out) or alone. 9 setups chosen on 2019-22 by profit / worst drop (R3 strict: +461%,
  drop 61%). Needed: beat the current vote's profit and buy-and-hold's worst drop in 2023-24
  and 2025+. Got +129% (vote +26%) but a 27.3% drop (hold 26.2%) in 2023-24, and -1.9% vs
  the vote's +20.7% from 2025. As a 7-day caller 45-53%. Not added.
- Fear & Greed index (alternative.me, free, from Feb 2018): with the v3 bar on 2018-24 two
  patterns held (extreme fear <= 20 +8.6 pts, a 7-day jump of 20+ +11.5 pts). Needed >= 55%
  at 7 days on 2025+ and above "always up" in each year. Rules: 50.0% of 48 (2025), 50.9%
  of 114 (2026). Logistic ML: 1 call at C = 0.003, 42.9% of 63 at C = 1. Not added, and
  not given to the LLM either.
- Ten more (rules + ML each, 20 strategies): calendar, halving cycle, trend momentum,
  volatility, volume, ETH/BTC, Coinbase premium, stablecoin supply (DefiLlama, from mid
  2020), on-chain (CoinMetrics community: MVRV, hash ribbon, active addresses), BTC vs
  Nasdaq. Rules = top / bottom fifth of each number kept with the v3 bar on 2017-24; ML =
  logistic C = 0.1 trained on 2017-24. Pass: >= 40 calls and >= 55% at 7 days on 2025+,
  beat a fair baseline (same Buy/Sell mix) in 2025 and 2026 each, circular-shift p < 0.0025
  (0.05 / 20). None passed. Closest: calendar ML 59.1% of 137 (p 0.16), on-chain rules
  55.6% of 117 (5 calls in 2025, all wrong), volatility ML 55.4% (2026 at 50%). The test
  was checked with fake agents: random ones fail; one right ~60% passes only sometimes
  (p 0.000-0.008), so a real edge below ~60% cannot be told from luck on 2025-26 alone.

- Round 2, 20 more (Oct 26 2026; scripts in the session scratchpad, not kept): 16 signal
  agents (rules + ML) - Binance taker buys, trade size, futures basis, Binance funding,
  Deribit DVOL, Kimchi premium (Upbit), Wikipedia views, net liquidity (WALCL - TGA - RRP),
  financial stress (VIX, NFCI, MOVE), policy uncertainty (EPU), gold and real yields, yen
  and yield curve, exchange flows (CoinMetrics), Puell / miner revenue, network fees and
  transactions, HYG / MSTR - and 4 pooled models over all 70 numbers (PCA + logistic,
  forest, gradient boosting, a learned combiner of the 6 rule / ML scores). Same test,
  luck bar raised to beating every circular shift (p < 0.0017). Passed: Kimchi rules (75.4%
  of 69, but 2 episodes, all Sells, and 0 / 54.5 / 28.9% when learned before 2021-23: not
  added) and financial stress ML (77.6% of 107, 15 episodes; added, below). The pooled
  models failed (48-51%); the learned combiner reached 57.9% (p 0.05).
- Round 3, 30 more (Oct 26 2026): candle shape, trading sessions (hourly), range volatility,
  distance from 1-year high/low, moving-average consensus, return autocorrelation, skew and
  fat tails, volume-price link, price-path analog (kNN), weekend moves, altcoin breadth,
  altcoin momentum vs BTC, USDT peg, Bitfinex USD and BTC lending rates, Bitfinex premium,
  CME positioning (CFTC), oil, copper/gold, China (FXI, yuan), semiconductors, 10-year yield
  and breakevens, M2, bank reserves and ECB assets, BAA credit spread, VVIX / SKEW, jobless
  claims, NVT, mining difficulty, event calendar (CPI days, expiries). BitMEX funding was
  blocked (403). New second bar: learned before each of 2021-2024 and judged on that year,
  every year with >= 30 calls >= 50% and above fair (at least 2 such years). None passed
  the first bar. Closest: VVIX/VIX rules 92.5% of 40 (36 in 2025; p 0.002 vs 0.0017),
  altcoin momentum ML 64.8% of 71 (p 0.03), volume-price ML 58.7% of 184 (p 0.07). The
  stress agent fails the new bar (2022 47%, 2023 48%).
- Oil redone (Oct 27 2026, WTI / Brent from Yahoo, not stored): of 14 top / bottom-fifth
  rules only "BTC 20-day move beat oil's by > 23 points -> Buy" held on 2017-24 (+8.6 pts).
  From 2025: 82.9% of 35 calls (2025 85.7% of 21, 2026 78.6% of 14) but under 40 calls and
  shift p 0.019; per year 2021-24 50.5 / 60.6 / 60.2 / 66.7% (2021 below fair). BTC's
  20-day move alone: 52.4% of 21, only 7 days shared, so oil does change the days. ML 36.4%.
  Not added; worth re-checking once 2027 adds calls.
- Markets that move with BTC (Oct 27 2026; 30 Yahoo series: crypto, crypto stocks, US
  indexes, tech, bonds, metals, energy, FX, VIX, Asia). Same-day links: IBIT +0.91, ETH
  +0.78, COIN / MSTR / SOL ~+0.55, Nasdaq / S&P ~+0.3 (+0.45 since 2025), VIX -0.25; none
  predicts BTC the next day or week (after their worst days BTC is down 42-53% vs 49%).
  Agents per market (5/20/60-day move, vs 50-day, BTC 20d minus it, 60-day corr; rules +
  logistic ML, 60 strategies, must beat every circular shift): none passed. Closest: HYG
  rules 65.5% of 148 (21 episodes, p 0.006, also 55/52/53/61% in 2021-24), USD/JPY rules
  62.8% of 218 (p 0.017), 10y-yield ML 72.4% of 98 (p 0.014, 2021 48%). With 60 tries one
  p ~0.006 is expected by luck. "BTC 20d beat the market by > ~20 pts -> Buy" was kept for
  nearly every market: it is BTC momentum, not the market.

## Financial stress domain (Oct 26 2026)
- `ai/stress/`: only `inputs.py` and `ml.py` (`rules = None`, `opus = None` in
  `__init__.py`). `ai/domains.has(agent, kind)` / `with_kind(kind)`: the Flow, prompts,
  Opus backtests, prompt comparisons, Signals and Profit columns skip kinds a domain lacks.
  AgentRun / DailyScore `rule_score` may be empty; Outcome has `stress_correct`, judged on
  the ML score when there is no rules or LLM score.
- Data: FRED VIXCLS (`vix`, +1 day) and NFCI (`nfci`, weekly, first print, dated by its
  Wednesday publication), Yahoo ^MOVE (`move_close`). `stress_snapshot`: VIX, its 20-day
  change, MOVE 20-day % change, NFCI (stale after 14 days).
- ML: logistic regression C = 0.1 on those 4 numbers, retrained monthly (as the macro
  forest). In the project (stored scores, NFCI as first published): 50.3% of 1056 calls in
  2019-22, 46.3% of 231 in 2023-24, 70.4% of 54 in 2025, 60.0% of 25 in 2026. (With revised
  NFCI it had looked like 48.8 / 28.2 / 62.8% of 86 / 61.1% of 54.)
- Since Oct 27 2026 it votes on its own in round 2 (see the 3-of-5 vote), not in the ML vote.
  Before that it voted in the ML group. From Oct 26 2026 the ML vote was macro + stress only
  (`decision_rule.VOTERS`): technical and derivatives ML were ~98% Buys and below "always up"
  (2019-24 52.8% / 50.4% vs 54.2%; 2026 43.5% / 45.3% vs 48.3%); they stay scored and shown.
  Vote (group lead 1, all agree): 54.0% of 626 on 2019-24 (+149%, worst drop 34%; with all 4
  ML: 53.8% of 617, +221%, 40%); 2025 on 72.3% of 94, +34.2%, drop 4% (rules + ML), with
  Haiku 68.5% of 54, +18.6% (hold -14.5%).
- build_memory defaults to 2025: a new agent needs `build_memory --agent X --start
  2017-08-17`. Memory is not in the score fingerprint, so after rebuilding memory delete
  all DailyScore rows and run build_scores (deleting one agent's rows is not enough: a day
  with any stored row counts as done).

## Risk-on day domain (Oct 27 2026)
- `ai/riskon/`: `inputs.py` and `rules.py` only (`ml = None`, `opus = None`). Rule: Bitcoin up
  today and the Nasdaq up today (its close vs its previous close; it must have traded that
  day) -> score 40 = Sell for tomorrow; anything else 50. Never Buys. Snapshot
  `indicator_service.riskon_snapshot` (binance close, yahoo nasdaq_close; the Nasdaq closes
  before Bitcoin's 24:00 UTC close, so both are known). No memory (build_memory skips it).
- Found by looking at 60 markets on 2017-2026: after Bitcoin and US stocks rise together,
  Bitcoin rises the next day less often. Most of the raw pattern is Bitcoin's own bounce
  after an up day (47% up next day after a BTC up day in 2017-24, gone from 2025: 49%).
- Hand-picked "BTC up + Nasdaq up -> Sell", next day: 52.1 / 54.2 / 56.6 / 51.8% in
  2018-19 / 2020-21 / 2022 / 2023-24 (fair 47.5 / 45.3 / 54.2 / 49.2), 58.4% of 149 from 2025
  (58.6% 2025, 58.1% 2026), luck p 0.045; holding BTC but out on its Sell days +52.7% vs
  -15.3%. Over 7 days a coin flip (51.4%). Not a clean test: the Nasdaq was picked after
  seeing 2025-26; a rules learner on 2017-24 picked only Solana (51.3%), an ML version 52.0%,
  "Sell after every BTC up day" 53.0%. Added on the user's request; judge it on new data.
- Same day, also tested and not added (scratchpad scripts): agents per market for the top 20
  markets by correlation with BTC (rules + logistic ML): none passed, best HYG rules 65.5%
  (p 0.006). Pairs of the top 10 (joint tertile rules, random forest; 94 strategies) and
  threes (median-split rules, forest; 170): none passed; the best (stock-index groups, ~60-65%
  from 2025, p 0.005-0.06) were 41-48% when learned before 2022 and 2023. All 10 together
  48-49%. Same-day correlation (IBIT +0.91, ETH +0.78) says nothing about tomorrow (next-day
  correlation -0.07 to +0.01).

## Same agents on other markets (Oct 27 2026, scratchpad script, nothing kept)
- Rules + ML unchanged (no LLM), only the asset's own data swapped in (ETH: Binance + Bybit;
  S&P 500: Yahoo OHLC, no derivatives; market-wide inputs unchanged), ML retrained on the
  asset's own outcomes; week = 7 days (5 trading days for the S&P). Bitcoin rerun the same
  way as a control matched the project (overall vote 56.6% on 2019-24).
- Overall vote (3 of 5, no LLM) vs "always up": ETH 2019-24 57.5% of 127 (+3.9 pts), 2025-26
  48.1% of 27 (+0.1); S&P 2019-24 64.6% of 65 (+3.1), 2025-26 75% of 12. Profit never near
  holding in 2019-24 (ETH +56% vs +2316%, S&P +23% vs +134%).
- ETH 2025-26 rules vote 61.6% and macro rules 66.6%: macro uses market-wide inputs, so it
  makes the same calls as on BTC; ETH moves with BTC, so it is not independent evidence.
- S&P: the BTC-tuned technical rules sell almost every day (38.9% / 41.5%); the ML agents
  learn "always buy" (= the base rate). Conclusion: nothing carries over beyond the small
  crypto edge of the vote (+2-4 pts over "always up" in 2019-24, unproven).

## Data audit, ETF flows and volatility (Oct 26 2026; scripts in the session scratchpad)
- Audit: no missing Binance days or impossible prices; Binance and Coinbase give the same
  7-day up/down on 99.2% of days; gaps are US holidays and the Oct 2025 shutdown (no October
  CPI). Bybit OI jumps > 30% on 12 days, mostly 2020-21. Found and fixed: CPI and NFCI were
  today's revised values (NFCI revisions: median 0.09, often bigger than a week's move), and
  January CPI was dated by February's seasonal-revision day, 2-5 days before its release.
  Now first prints dated by publication (see Data). Macro barely moved; stress made fewer calls.
- ETF flows (Jan 2024 on, learned on 2024 only): rules 50.1% of 351 (fair 50.2), ML 49.9% /
  walk-forward 45.4%; macro forest + flows 56.7% of 215 vs 57.9% of 202 without. Flows follow
  price (corr 0.51 with the past week). No edge; they stay only in the macro LLM input.
- CPI gap (Nov 11 2026): `macro_snapshot` took the last 13 prints as 13 consecutive months, but
  October 2025 is missing, so from the Dec 18 2025 print year-on-year inflation covered 13
  months (4.00% instead of 3.68% on the latest print) and November's two-month change was read
  as one month's. Now `macro.every_month` places prints by their real month and fills a missing
  one at the steady rate between its neighbours; a two-month print counts at its monthly rate
  and stays out of its own trend. A CPI print stored without its month gives no CPI numbers
  (`collect_data --source fred --start 2015-12-01` once on an old database). 7-day hit rates
  before -> after (days to Oct 19 2026): macro rules 2019-24 52.2% of 1185 and 2025 67.3% of
  269 unchanged, 2026 63.2% of 171 -> 57.3% of 143; macro ML 2019-24 51.3% of 1492 and 2025
  55.6% of 142 unchanged, 2026 57.3% of 75 -> 58.7% of 104. The rules lost 29 Sells in Jan-Feb
  2026 (inflation really was below 2.7%, a Buy point that cancels the CPI Sell) that happened
  to be right. The macro rule thresholds were tuned on the wrong numbers and were not re-tuned.
- Volatility instead of direction: HAR + VIX / MOVE / DVOL / funding / OI predicts next week's
  volatility ~25% better than "same as last month" (2025 and 2026), but sizing positions by it
  did not beat holding on Sharpe in 2019-24 (1.14 vs 1.15; worst drop 74.5 vs 76.6%) and only
  a little from 2025 (-7.6% vs -13.2%). Big-drop (>= 8% in a week) warning: AUC 0.52 in 2025,
  0.25 in 2026. Not added.

## Strong signal with the dollar agent (Nov 11 2026)
- Two strong signals are shown side by side (the user's choice, "show both"); neither changes a
  call. "Strong (4 of 5)" is unchanged (`STRONG_NEEDED`, `strong_call`). "Strong + dollar"
  (`strong_dollar_call`): six voters, the five of round 2 plus the dollar ML agent
  (`STRONG_ONLY`, `STRONG_VOTERS`), strong when Buy votes minus Sell votes is >= `STRONG_NET` = 4
  either way, so an opposing vote counts against it. The dollar agent votes nowhere else.
- `ai/dollar/`: `inputs.py` and `ml.py` only (`rules = None`, `opus = None`). Snapshot
  `indicator_service.dollar_snapshot`: the dollar index's 5 / 20 / 60-session change, distance
  from its 50-session average, Bitcoin's 20-session move minus the dollar's, their 60-session
  correlation (math in `indicators/relative.py`; Bitcoin compared on the index's trading days;
  stale after 5 days). ML: logistic C = 0.1, retrained monthly. Outcome has `dollar_correct`.
- Test, bar written first: 17 ways to count (other extra voters, other leads) chosen on 2019-24
  only (>= 15 judged trades, highest edge over fair); replace the old signal only if its 2019-24
  edge is better AND from 2025 it has >= 10 trades and >= 80% right. Trades = days in a row with
  the same call, judged on the first day after 7 days.
- In the project (stored scores): Strong (4 of 5) 8 of 13 (61.5%) on 2019-24, 9 of 10 (90%)
  from 2025. Strong + dollar 36 of 52 (69.2%) on 2019-24, 10 of 13 (76.9%) from 2025; per year
  2019 5/11, 2020 8/9, 2021 12/14, 2022 5/9, 2023 6/9, 2025 6/8, 2026 4/5. The scratch run gave
  38 of 53 and 10 of 12 (83%), shift p 0.006 / 0.029; in the project it missed the 80% bar, so
  it did not replace the old signal. The overall vote itself: 81 of 134 (60.4%), 31 of 52 (59.6%).
- The dollar agent alone is weak: 94 of 165 trades (57.0%) on 2019-24, 17 of 37 (45.9%) from
  2025, and ~96-99% Buys (see "Bigger vote"). It was the best of 17 tries, so expect less on new
  data; four times the trades on 2019-24 is its real advantage over the old signal.
- Pages: Today shows both badges, a third track-record tile and a dollar row in "Who voted"
  ("votes only in Strong + dollar"); Signals and Profit have a "Strong + dollar" column / row.
  The agent has memory from 2017-08-17 and stored scores; live runs start with the next daily_run.

## Search for 70% of calls right (Nov 11 2026, scratchpad scripts, nothing added)
- Bar written before any result: learn to 2022, choose on 2023-24, test once on 2025 on; pass =
  test >= 70% at 7 days (5 trading days for stocks), >= 30 separate episodes, >= fair + 10 points,
  circular-shift p < 0.01, choose period >= 65%, no market under 55%. No horizon change and no
  profit-target exits (both raise the win rate without an edge). Nothing passed.
- Strict agreement of the 5 round-2 voters, 2025 - Oct 26 2026: 4 of 5 = 88.9% of 18 calls, 9 of
  10 episodes (p 0.010), but 5 of the 10 are one rally (Apr 11 - May 11 2025) and there is no LLM
  vote before 2025 to check it on. 5 of 5 never happened (risk-on never Buys). Without the LLM,
  "all 4" made 14 calls in 2019-24 (9 right, all Sells). The 3-of-5 vote: 68.6% of 105 calls but
  58.8% of 51 episodes; 59.2% in 2019-22 and 50.0% in 2023-24 (104 Sells in a rising market).
- Each agent only at an extreme score (cut-off 60-75 chosen on 2023-24): best macro ML >= 60,
  65.0% of 40 (9 episodes); it was 36.2% on 2023-24.
- Literature rules on 24 markets (9 crypto, 8 stock indexes, gold, silver, oil, copper, TLT,
  EUR/USD, USD/JPY; Yahoo, not stored): dip in an uptrend (close > 200-day, RSI(2) < 5) 64.1% of
  270 pooled from 2025, crypto 52.5%, stock indexes 71.0% of 100 (p 0.04) - but on the indexes it
  was 52-63% in every 2-4 year block of 2005-2022 against a 53-61% base rate, so 2025-26 is the
  outlier. 7-day momentum (top fifth) 46.5%. Panic fading (VIX > 30 and falling) 80.4% of 56 but
  one week (April 2025).
- One model pooled over the 24 markets (21 volatility-scaled price features + VIX / dollar,
  gradient boosting and logistic, each year predicted from earlier years), speaking only above
  a probability cut-off: no cut-off ever reached 70% on earlier predicted years, so by the rule it
  stayed silent. Its confident Buys were 55-59% in 2013-22 (Sells below 50%); 78% of 69 at 0.65
  from 2025, a cut-off that gave 59% in 2019-22.
- Reading: honest 7-day direction is ~50-58%, as published work finds. A 70% that holds needs
  either evidence that does not exist yet (4 of 5: ~5 episodes a year, so years to prove) or a
  different question. Open and paid: Haiku on 2019-24 (~$3.50) would test 4 of 5 on six more years.

## Bigger vote: 7 or 9 voters (Nov 11 2026, scratchpad scripts, nothing switched)
- Rule written first: 18 new walk-forward agents (monthly logistic C = 0.1 on a series' 5/20/60-day
  move, distance from its 50-day, BTC 20-day minus it, 60-day correlation: HYG, 10-year yield,
  VVIX/VIX, USD/JPY, gold, oil, copper, TLT, dollar, Nasdaq, SMH, ETH/BTC; altcoin breadth, volume,
  calendar, BTC momentum, the pooled 24-market model for BTC, the dip rule). Eligible on 2019-24
  only (2019-22 >= fair + 2 with 100 calls, 2023-24 >= fair): dollar, VVIX/VIX, ETH/BTC, pooled
  model. Dollar and VVIX/VIX are 96-99% Buys and agree on 98.5% of days: two near-permanent Buy votes.
- Test 2025 - Oct 26 2026 (current 3 of 5: 68.6% of 105 calls, 58.8% of 51 episodes): 7 voters
  (+ dollar, VVIX/VIX), 5 needed: 88.5% of 26, 8 of 9 episodes, all Buys, no call in 2023-24,
  63.2% of 117 in 2019-22. 9 voters, 5 needed: 72.7% of 55, 15 of 20 episodes. Stress replaced
  by dollar (stress was below fair on 2019-24), 3 needed: 63.9% of 166, 60.0% of 65 episodes,
  +68.8% vs +31.5%; 4 needed: 84.6% of 26, 14 of 17 episodes. "Worth switching" needed a better day
  and episode hit rate than the current vote with >= 26 episodes and a better 2023-24: none did.
- Independence (both called, 2019 - Oct 2026): ML-type agents are wrong together 1.2-2.3 times as
  often as independent ones would be (macro ML / stress 1.71, dollar / VVIX 2.29); the Rules vote
  and the risk-on day are wrong with the others less often than chance (0.7-0.9), because they
  lean the other way. Seven independent voters right 55% each would give a ~61% majority, 31 would
  give ~71%; ours are not independent, so more agents of the same kind cannot reach 70%.

## Is the ML useless? and a monthly call (Nov 11 2026, scratchpad scripts, nothing changed)
- Rule written first: ML goes if a vote without it has an edge over fair (hit rate - fair) at
  least as big as the current vote's in 2019-22 AND in 2023-24. Edge 2019-22 / 2023-24, then
  2025 - Oct 26 2026: current +8.3 / +6.8 (68.6% of 105, episodes 58.8% of 51); without stress
  +7.7 / +0.9 (59.9% of 347); without the ML vote +5.6 / +2.8 (64.7% of 275); no ML at all
  (Rules vote, LLM, risk-on; 2 needed) +19.5 / +1.5 (65.0% of 243, episodes 61.6% of 125); no ML
  with the three rule agents voting one by one +9.8 / +2.2 (64.9% of 282, episodes 65.6% of 61).
  Every vote without ML fell apart in 2023-24 (132-311 Sells in a rising market, 44-46% right):
  the ML voters lean Buy and stop the bearish rules from selling a rally. ML stays.
- The no-ML votes made far more from 2025 (long / short, 7-day hold, after fees: +166% to +247%
  vs +31.5%) and lost 74-88% in 2023-24: the rules were tuned on 2025-26, so that profit is
  in-sample.
- Monthly call (30 days crypto, 21 trading days elsewhere; 24 markets; calls a month apart per
  market): "always Buy" is right 54.9% (stock indexes 59-66%) with no skill. Trend rule (above
  the 200-day and 50 > 200 -> Buy, below both -> Sell): 51.4% of 2795 calls on 2013-24 (fair 52.3),
  52.5% of 503 from 2025 (fair 56.0); its Sells 45.6% / 44.8%. Pooled models for the monthly
  outcome: confident Buys 55-57% on 2013-24, no cut-off reached 70% on earlier years, silent.
  A longer horizon adds no edge; a high hit rate there is only the market's drift.

## Agents talking to each other: debate test (Oct 26 2026, $0.30, scratchpad script)
- Round 2 for the Haiku v3 agents: same input plus their own first answer and every other
  agent's score that day (rules, ML, the other LLMs' scores and reasons); final answer. Every
  4th day from 2025 (164 days x 3 = 492 calls via opus_client, logged with tokens and cost).
- Formally passed (hit rate and Brier better in 2025 and 2026): 72.1% of 43 vs 68.9% of 45,
  55.7% of 61 vs 54.8% of 62; Brier 0.2478 vs 0.2489, 0.2483 vs 0.2492. But the same number
  of calls were right (31, 34): it only dropped 1-2 wrong ones. Scores moved 0.8 points on
  average, 209 of 255 changes toward the others (herding); the overall vote was unchanged on
  every day. Not added. Pooled models and a learned combiner (round 2) also failed.

## Model comparison: Haiku vs Opus (Oct 2026)
- AI_MODEL is claude-haiku-5-5 since Oct 26 2026 (the user's .env). Pages name the LLM from
  it (`ai.opus_client.model_label`, context processor `llm_label`); internal keys and the
  `opus_score` field keep the old name. The comparison reference stays Opus 5.5
  (`model_comparison_service.REFERENCE`), whatever AI_MODEL is.
- Tests run with AI_MODEL = Opus whatever .env says (`tests/runner.py`).
- `AgentRun.model` records the Claude model asked (old runs back-filled as Opus 5.5). Opus
  queries (Signals, opus_scores, backtest_opus) read only AI_MODEL's runs, so comparison
  runs never mix in. Prices per model in `ai/opus_client.PRICES_PER_MTOK`; a model without
  prices is never called.
- `python manage.py compare_models [--model claude-haiku-5-5] [--estimate] [--max-cost 0.50]
  [--report]`: replays AI_MODEL's saved backtest questions (same prompt version, same saved
  model input) to the other model, once per day and agent, then compares at 1/3/7 days.
- Result on the 30 Opus test days x 3 domains (Jul 1-20, Oct 4-13, prompt v2): Haiku's
  scores were within 1.7 points of Opus on average, same Buy/Sell/Hold on 78 of 90; 7-day
  hit rate 33.3% of 33 calls vs Opus 35.5% of 31, Brier 0.262 vs 0.260. Cost $0.048 vs
  $1.38 (~29x cheaper). Both did badly on these mostly falling days; 90 answers is too few
  to call either good, only that Haiku answers almost the same.
- Page `/models/` (`apps/dashboard/services/model_service.py`, `static/js/models.js`): tabs
  for All agents / Technical / Derivatives / Macro switched in the browser (remembered, and
  `#macro` links work); per agent both models' hit rate, Brier, cost, agreement, a score
  chart and every day's two calls side by side. `?horizon=1|3|7`, `?model=` if several.

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

**Current step:** done through 14, dollar ML agent (6th domain) and a second strong signal "Strong + dollar" shown beside "Strong (4 of 5)", risk-on day rules agent (5th domain), overall vote 3 of 5
(Rules, ML, LLM votes, stress, risk-on day), financial stress ML agent (4th domain), rule search, Signals page, `ai/` package with rules / ML / Opus agents per domain run by a CrewAI Flow, macro ML is a random forest, two-round vote (Rules / ML / Opus votes; overall only when all agree). Pending for the user: crontab; optionally rerun the technical and derivatives Opus backtests, which would create prompt v3 (paid, ~$0.45 each).
