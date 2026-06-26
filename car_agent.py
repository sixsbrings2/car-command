#!/usr/bin/env python3
"""
Car Command — main agent.

Pipeline:  config -> Auto.dev fetch -> Claude scoring -> data/listings.json

Run locally:   python car_agent.py
On a schedule:  via .github/workflows/car-search.yml
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from sources import autodev
from scoring import claude_scorer

ROOT = Path(__file__).parent
CONFIG_PATH = ROOT / "config.yaml"
OUTPUT_PATH = ROOT / "data" / "listings.json"


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def main() -> int:
    cfg = load_config()

    print("Fetching listings from Auto.dev ...")
    raw = autodev.fetch_listings(cfg)
    print(f"  {len(raw)} listings matched the hard filters.")

    if not raw:
        print("  Nothing to score. Writing empty feed.")
        scored = []
    else:
        print("Scoring with Claude ...")
        scored = claude_scorer.score_listings(cfg, raw)
        print(f"  {len(scored)} listings kept after scoring (min_score="
              f"{cfg['output']['min_score']}).")

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "criteria": cfg["search"],
        "count": len(scored),
        "listings": scored,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"Wrote {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
