# Car Command

An AI-scored Range Rover acquisition feed for the Lake Norman area — the same
architecture as Pipeline Command, pointed at used-car inventory instead of jobs.

```
config.yaml  →  Auto.dev listings  →  Claude scoring  →  data/listings.json  →  dashboard
   criteria       (data source)        (AI judgment)        (ranked feed)       (GitHub Pages)
```

A scheduled GitHub Action runs the agent on weekday mornings. Auto.dev returns
every used Range Rover that matches the hard filters; Claude scores each one 0–100
against the nuanced preferences (color, mileage sweet spot, trim, value, title
red flags) and writes a ranked feed the dashboard reads.

## Where the AI lives

This is the part worth documenting. The pipeline has a deterministic half and an
AI half, and keeping them separate is the whole point.

| Stage | What it does | AI? |
|-------|--------------|-----|
| Auto.dev fetch (`sources/autodev.py`) | Pulls listings matching make/model/year/price/location | No — plain API filtering |
| Claude scoring (`scoring/claude_scorer.py`) | Reads each listing + description, returns score, one-line verdict, and flags | **Yes — the judgment layer** |
| Ranking (`car_agent.py`) | Sorts by score, drops below threshold, keeps top N | No — deterministic |
| Dashboard (`docs/index.html`) | Renders the ranked feed | No |

The AI element is specifically: **weighing tradeoffs no filter can express** (a
low-miles black Autobiography vs. a cheaper higher-miles gray HSE) and **reading
free-text descriptions for things filters miss** (accident history, "as-is"
wholesale language, branded titles). Same role Claude plays in Pipeline Command.

## Setup

1. **Keys.** Get an Auto.dev key (free Starter tier: 1,000 calls/mo) and an
   Anthropic API key. Copy `.env.example` to `.env` and fill both in for local runs.
2. **Install.** `pip install -r requirements.txt`
3. **Run once.** `python car_agent.py` → writes `data/listings.json`.
4. **View.** Open `docs/index.html` (served, not file://, so the fetch works).

## Schedule it

Add two repo secrets under **Settings → Secrets → Actions**: `AUTODEV_API_KEY`
and `ANTHROPIC_API_KEY`. The workflow in `.github/workflows/car-search.yml` then
runs weekdays at 8AM EST, re-scores, and commits the refreshed feed. You can also
trigger it manually from the Actions tab.

## Publish the dashboard

**Settings → Pages → Source: deploy from branch**, folder `/docs`. The feed lives
at `../data/listings.json` relative to the page, so it updates whenever the Action
commits a new run.

## Tuning

Everything you'd want to change lives in `config.yaml` — models, ZIP, radius,
price/year/mileage bounds, preferred colors, the score threshold, and how many
listings to keep. The code never needs editing to adjust the search.

## Swapping the data source

`sources/autodev.py` is the only file that knows about Auto.dev. To move to
MarketCheck or another provider, write a module exposing
`fetch_listings(cfg) -> list[dict]` that returns the same normalized fields, and
import it in `car_agent.py`. Scoring, ranking, and the dashboard stay untouched.
