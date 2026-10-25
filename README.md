# BTC Advisor

A local multi-agent tool that advises on daily Bitcoin trades. Three independent agents
(technical analysis, derivatives, macro) each produce a rule-based score computed in code and
a judgment score from Claude Opus. A trade is suggested only when the agents agree above a
confidence threshold. The system never places trades.

See `docs/project_plan.pdf` for the full plan and `CLAUDE.md` for progress.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in SECRET_KEY, ANTHROPIC_API_KEY, FRED_API_KEY
python manage.py migrate
python manage.py test
```
