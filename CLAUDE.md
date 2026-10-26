# BTC Advisor — notes for Claude Code

A local Django tool that advises Ayham on daily Bitcoin trades. Three domains (technical,
derivatives, macro) each have three independent agents: rules (code), ML (walk-forward:
logistic regression, random forest for macro) and Opus 5.5 (judgment). A fourth domain,
financial stress, has only an ML agent (see "Financial stress domain"). The system only advises; Ayham places trades manually. Full plan:
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

## Combining rule: the two-round vote (replaces step 10's thresholds)
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
- Combining-rule thresholds start at 55: a score of 50 means "no edge" and never buys.

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
  each Signals column (9 agents, Rules / ML / LLM votes, overall vote) as a strategy: Buy =
  long close D to close D+1; Sell = flat, or short with `short`. Profit, vs holding, worst
  drop, trades, trades won, coverage, and one chart line per agent. `profit_service.py` builds
  it from score_store + LLM runs; math in `metrics.py` (positions 1 / 0 / -1). Filters and sort
  are client-side in `static/js/profit.js` (localStorage "profit-filters"). Free.

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

## Financial stress domain (Oct 26 2026)
- `ai/stress/`: only `inputs.py` and `ml.py` (`rules = None`, `opus = None` in
  `__init__.py`). `ai/domains.has(agent, kind)` / `with_kind(kind)`: the Flow, prompts,
  Opus backtests, prompt comparisons, Signals and Profit columns skip kinds a domain lacks.
  AgentRun / DailyScore `rule_score` may be empty; Outcome has `stress_correct`, judged on
  the ML score when there is no rules or LLM score.
- Data: FRED VIXCLS (`vix`, +1 day) and NFCI (`nfci`, weekly, dated +6 days: Friday's week
  is published Wednesday), Yahoo ^MOVE (`move_close`). `stress_snapshot`: VIX, its 20-day
  change, MOVE 20-day % change, NFCI (stale after 14 days).
- ML: logistic regression C = 0.1 on those 4 numbers, retrained monthly (as the macro
  forest). In the project (stored scores): 48.8% of 1017 calls in 2019-22, 28.2% of 71 in
  2023-24 (mostly wrong Sells), 62.8% of 86 in 2025, 61.1% of 54 in 2026 (all Buys).
- It votes in the ML group (4 voters). Vote re-chosen: group lead 1, all agree -> 52.6% of
  572 on 2019-24; 2025 on 72.4% of 134 calls, +35.0% (rules + ML; was 75.3% of 93, +21.7%),
  with Haiku 69.3% of 88, +13.9%.
- build_memory defaults to 2025: a new agent needs `build_memory --agent X --start
  2017-08-17`. Memory is not in the score fingerprint, so after rebuilding memory delete
  all DailyScore rows and run build_scores (deleting one agent's rows is not enough: a day
  with any stored row counts as done).

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

**Current step:** done through 14, financial stress ML agent (4th domain, votes in the ML group), rule search, Signals page, `ai/` package with rules / ML / Opus agents per domain run by a CrewAI Flow, macro ML is a random forest, two-round vote (Rules / ML / Opus votes; overall only when all agree). Pending for the user: ETF CSV, crontab; optionally rerun the technical and derivatives Opus backtests, which would create prompt v3 (paid, ~$0.45 each).
