"""
The AI layer.

Auto.dev hands us listings that already match the hard filters (make, model,
year, price, location). What it can't do is *judge* — weigh a low-mileage black
Autobiography against a cheaper but higher-mileage gray HSE, or notice "minor
accident reported" buried in a description. That judgment is what Claude does here.

Each listing gets:
  - score      : 0-100 fit against Travis's criteria + preferences
  - verdict    : one-line human summary
  - flags      : list of concerns (title issues, color miss, high miles, etc.)

This mirrors Pipeline Command exactly: deterministic source → Claude scoring → ranked feed.
"""

from __future__ import annotations

import os
import json
import anthropic

MODEL = "claude-opus-4-8"
BATCH_SIZE = 8   # listings per API call; keeps prompts focused and cheap


def _client() -> anthropic.Anthropic:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Add it as a repo secret or to your .env."
        )
    return anthropic.Anthropic()


def _build_prompt(cfg: dict, batch: list[dict]) -> str:
    prefs = cfg["preferences"]
    criteria = f"""You are a sharp used-car buyer's analyst scoring Range Rover listings for a
specific buyer near ZIP {cfg['search']['zip']} (Lake Norman, NC).

The buyer's criteria and preferences:
- Models in scope: {", ".join(cfg['search']['models'])}
- Strongly preferred exterior colors: {", ".join(prefs['exterior_colors'])}.
  A listing outside these colors is not disqualified but should lose points.
- Mileage sweet spot is around {prefs['mileage_sweet_spot']:,} miles; lower is better.
  Hard ceiling is {cfg['search']['mileage_max']:,} miles.
- Price window: ${cfg['search']['price_min']:,}-${cfg['search']['price_max']:,}.
- Value: {prefs['value_anchor']}
- Trims: {prefs['trim_notes']}

Score each listing 0-100 on overall fit. Be discriminating — most listings should
land 50-85; reserve 90+ for genuinely excellent matches (preferred color, low miles,
strong trim, fair price, clean title) and push obvious problems below 50.

Return ONLY a JSON array, no prose, no markdown fences. One object per listing in the
SAME ORDER given, each with exactly these keys:
  "vin"     : the listing's VIN (copy it back)
  "score"   : integer 0-100
  "verdict" : one sentence, under 20 words, plain and specific
  "flags"   : array of short strings (empty array if none)
"""
    listings_block = json.dumps(
        [
            {
                "vin": x.get("vin"),
                "year": x.get("year"),
                "model": x.get("model"),
                "trim": x.get("trim"),
                "color": x.get("exterior_color"),
                "mileage": x.get("mileage"),
                "price": x.get("price"),
                "title_status": x.get("title_status"),
                "cpo": x.get("cpo"),
                "dealer": x.get("dealer_name"),
                "description": (x.get("description") or "")[:600],
            }
            for x in batch
        ],
        indent=2,
    )
    return f"{criteria}\n\nLISTINGS:\n{listings_block}"


def _score_batch(client, cfg: dict, batch: list[dict]) -> dict[str, dict]:
    msg = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        messages=[{"role": "user", "content": _build_prompt(cfg, batch)}],
    )
    text = "".join(b.text for b in msg.content if b.type == "text").strip()
    # Be forgiving if the model wraps output in fences despite instructions.
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        # If a batch fails to parse, don't kill the whole run — skip it.
        return {}
    return {row["vin"]: row for row in parsed if row.get("vin")}


def score_listings(cfg: dict, listings: list[dict]) -> list[dict]:
    """Attach score/verdict/flags to each listing, then rank and trim."""
    client = _client()
    scores: dict[str, dict] = {}

    for i in range(0, len(listings), BATCH_SIZE):
        batch = listings[i : i + BATCH_SIZE]
        scores.update(_score_batch(client, cfg, batch))

    enriched = []
    for x in listings:
        s = scores.get(x.get("vin"))
        if not s:
            continue
        x["score"] = int(s.get("score", 0))
        x["verdict"] = s.get("verdict", "")
        x["flags"] = s.get("flags", [])
        enriched.append(x)

    min_score = cfg["output"]["min_score"]
    enriched = [x for x in enriched if x["score"] >= min_score]
    enriched.sort(key=lambda x: x["score"], reverse=True)
    return enriched[: cfg["output"]["top_n"]]
