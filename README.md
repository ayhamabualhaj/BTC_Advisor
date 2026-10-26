# BTC Advisor

A local multi-agent tool that advises on daily Bitcoin trades. Three domains (technical
analysis, derivatives, macro) each have three independent agents, run together by a CrewAI
Flow. A fourth domain, financial stress (VIX, MOVE, NFCI), has only an ML agent; a fifth,
the risk-on day (Bitcoin and the Nasdaq both up today -> Sell for tomorrow), only a rules
agent. The ML vote is the macro ML agent (technical and derivatives ML are shown but do not vote):

- a **rules** agent: a score computed in code from explicit criteria (start at 50, criteria add or subtract);
- an **ML** agent: logistic regression on the domain's numbers, retrained every day on past
  days whose 7-day outcome was known (free);
- an **Opus** agent: Claude Opus 5.5's confidence (0-100) that the price is higher in
  7 days, with 3-5 reasons and a suggested stop loss.

A buy comes from a two-round vote: the rules, ML and Opus agents each vote among their
domains; then five voters (those three votes, the financial stress agent and the risk-on day)
give the overall vote, Buy or Sell when 3 of the 5 agree (group lead chosen on 2019-2024,
tested on 2025 onward). The Today page shows who voted what. The system only advises; it
never places trades.

The full plan is in `docs/project_plan.pdf`; conventions and progress in `CLAUDE.md`.

## Setup

Python 3.13 (CrewAI does not support 3.14 yet) and a running PostgreSQL server.

```bash
python3.13 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`:

| Setting | What it is |
|---|---|
| `DB_NAME`, `DB_USER`, `DB_PASSWORD` | The PostgreSQL database, user and a password you choose |
| `SECRET_KEY` | Any long random string (`python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"`) |
| `ANTHROPIC_API_KEY` | For the Opus scores. Without it everything runs on rule scores only. |
| `FRED_API_KEY` | Free key from https://fred.stlouisfed.org/docs/api/api_key.html (Fed rates, CPI, 2-year yield) |
| `AI_EFFORT` | Opus thinking effort: `low`, `medium` (default), `high`… Higher costs more. |

Then create the PostgreSQL user and database from those settings (asks for your sudo
password once; the user gets CREATEDB so the tests can make their own database), load the
history and build the memory:

```bash
bash scripts/setup_postgres.sh
python manage.py migrate
python manage.py collect_data            # Aug 2017 to yesterday, all sources (~2 min)
python manage.py build_memory            # past setups + outcomes for RAG (free, ~10 s)
python manage.py test                    # 179 tests, no network, no API calls
```

**Spot Bitcoin ETF flows** come from farside.co.uk, which blocks scripts. Open
https://farside.co.uk/bitcoin-etf-flow-all-data/ in a browser, select the whole table
(header row with "Total" included), copy it, paste it into a text editor and save it as
`data/imports/etf_flows.txt` (git-ignored: raw copies of other sites' tables stay local). A CSV or the pasted text both work; days where no fund
reported (holidays, today) are skipped. Each day's flow is dated the next day (it is complete only after the
US close). Then:

```bash
python manage.py import_etf_flows data/imports/etf_flows.txt
```

## Daily use

```bash
python manage.py daily_run               # collect, run agents for yesterday (UTC), decide
python manage.py runserver               # dashboard at http://127.0.0.1:8000/
```

`daily_run` costs about 3 Opus calls a day; it refuses to run the same day twice unless you
pass `--force`, and falls back to the rules and ML agents (free) when no API key is set (or
with `--rules-only`).

### Run it automatically (cron)

Daily candles close at 00:00 UTC. Add to `crontab -e` (adjust the path):

```cron
CRON_TZ=UTC
# The decision for the day that just closed.
15 0 * * * cd /home/lime/PycharmProjects/BTC_Advisor && .venv/bin/python manage.py daily_run >> daily_run.log 2>&1
# OKX keeps only ~24 hours of liquidations, so collect them several times a day.
0 */4 * * * cd /home/lime/PycharmProjects/BTC_Advisor && .venv/bin/python manage.py collect_data --source okx --start $(date -u -d '2 days ago' +\%F) >> collect.log 2>&1
```

## Backtesting and tuning

The test period starts on 2026-07-01, after Opus 5.5's training cutoff.

```bash
python manage.py backtest_rules                    # rule scores: each agent alone + combined (free)
python manage.py backtest_rules --scores ml        # the same for the ML agents (free)
python manage.py calibration --scores rules        # is a 70 right 70% of the time? (free, also --scores ml)
python manage.py build_scores                      # store every day's rules + ML scores since 2019 (free, ~2 min)
python manage.py choose_combining_rule             # choose the vote on 2019-2024, test on 2025+ (free)

python manage.py backtest_opus --estimate          # calls needed and expected cost (free)
python manage.py backtest_opus --agent technical --max-cost 2   # PAID; resumes where it stopped
python manage.py backtest_opus --max-cost 30       # all three agents
python manage.py calibration --scores opus
```

Each agent gets only data dated on or before the decision day, as relative numbers (no
prices, no dates, no coin name), plus its 5 most similar past setups whose 7-day outcome was
already known.

## Other commands

| Command | What it does |
|---|---|
| `collect_data [--source X] [--start --end]` | Pull data again; lists missing days |
| `score_rules [--date] [--save]` | Rule scores for one day |
| `run_agents [--date] [--agent X]` | Rules + Opus for one day, prints the JSON output (paid) |
| `build_memory [--start --end]` | Rebuild the RAG memory |

## Dashboard and API

Pages: **Today** (decision, each agent's scores, reasons, stop loss), one page per agent
(score chart, data used, live/backtest runs), **Signals** (month by month since 2019 and an all-months overview: every Buy/Sell/Hold call from
each domain's rules, ML and Opus agent, the Rules / ML / Opus votes and the overall 3-of-5 vote, with confidence and result, green when right and red when wrong after 1, 3 or 7 days), **Profit** (what following each of the 11 agents and the 4 votes would have earned vs buy-and-hold, any period, stay out or go short on Sell, filter by agent and kind), **Models** (Opus vs Haiku on the same questions, one tab per agent), **Backtests** (profit vs buy-and-hold,
calibration, combining rule), **Costs** (API spend per agent and day), **Prompts** (every
prompt version and its results). Editing an agent's `prompt.md` creates a new prompt
version automatically on the next run.

Read-only JSON API under `/api/`: `decision/today/`, `agent-runs/?agent=&backtest=&date=`,
`backtests/?name=`, `costs/`, `prompts/?agent=`.

## Layout

```
config/            settings, urls
scripts/           setup_postgres.sh
apps/data/         MarketData, collectors (Binance, Bybit, OKX, Yahoo, FRED, Farside CSV), indicators
ai/                technical/ derivatives/ macro/ (inputs.py, rules.py, ml.py, opus.py, prompt.md),
                   flow.py (CrewAI Flow), ml.py, opus_client.py, similarity.py (RAG distance)
apps/agents/       AgentRun, PromptVersion, MemoryCase; services that prepare, run and save the agents
apps/backtest/     metrics, calibration, combining rule, daily run, outcomes, Decision, BacktestRun
apps/dashboard/    REST API and pages (views -> services -> repositories)
templates/ static/ HTML templates, CSS, Chart.js helpers
tests/             unit and integration tests (a fake Anthropic client, no paid calls)
```

## Known limits

- **Liquidations** have no free history (OKX keeps ~24 h), so that rule only works going
  forward once the 4-hourly cron is running.
- **Stand-ins for paid data:** "Fed cut expected" = 2-year yield 0.25 below fed funds;
  "CPI vs expectations" = latest monthly CPI change vs the previous 3 months.
- **Small test period:** about 115 days since July 2026, so backtest numbers and the chosen
  combining rule are fragile. On rule scores alone, every strategy trailed buy-and-hold.
