"""
Auto.dev listings adapter.

This is the *data acquisition* layer. It is deliberately the only file that knows
anything about Auto.dev. Swap in MarketCheck or another provider by writing a new
module that exposes the same `fetch_listings(cfg) -> list[dict]` signature and
returns the same normalized listing shape. Nothing downstream changes.

API docs: https://docs.auto.dev/v2/products/vehicle-listings
Auth: Bearer token in the AUTODEV_API_KEY env var.
"""

from __future__ import annotations

import os
import time
import requests

BASE_URL = "https://api.auto.dev/listings"

# Auto.dev Starter plan caps ?limit= at 20. Growth=100, Scale=500.
PAGE_LIMIT = 20
MAX_PAGES = 10          # safety stop; 10 * 20 = 200 raw listings is plenty pre-scoring
REQUEST_TIMEOUT = 30


def _headers() -> dict:
    key = os.environ.get("AUTODEV_API_KEY")
    if not key:
        raise RuntimeError(
            "AUTODEV_API_KEY is not set. Add it as a repo secret (GitHub Actions) "
            "or to your local .env. Get a key at https://www.auto.dev/"
        )
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _build_params(cfg: dict, model: str, page: int) -> dict:
    s = cfg["search"]
    params = {
        "vehicle.make": s["make"],
        "vehicle.model": model,
        "zip": s["zip"],
        "distance": s["distance_miles"],
        "vehicle.year": f"{s['year_min']}-{s['year_max']}",          # inclusive range
        "retailListing.price": f"{s['price_min']}-{s['price_max']}",  # inclusive range
        "sort": "updatedAt.desc",
        "page": page,
        "limit": PAGE_LIMIT,
    }
    return params


def _normalize(raw: dict) -> dict:
    """Flatten Auto.dev's nested response into the shape the rest of the app expects."""
    vehicle = raw.get("vehicle", {}) or {}
    retail = raw.get("retailListing", {}) or {}
    dealer = retail.get("dealer", {}) or raw.get("dealer", {}) or {}

    return {
        "vin": vehicle.get("vin") or raw.get("vin"),
        "year": vehicle.get("year"),
        "make": vehicle.get("make"),
        "model": vehicle.get("model"),
        "trim": vehicle.get("trim"),
        "exterior_color": vehicle.get("exteriorColor") or vehicle.get("color"),
        "mileage": vehicle.get("mileage") or vehicle.get("miles"),
        "price": retail.get("price"),
        "title_status": retail.get("titleStatus"),
        "cpo": retail.get("cpo"),
        "condition": retail.get("condition") or vehicle.get("condition"),
        "dealer_name": dealer.get("name"),
        "city": retail.get("city") or (raw.get("location") or {}).get("city"),
        "state": retail.get("state") or (raw.get("location") or {}).get("state"),
        "url": retail.get("vdpUrl") or retail.get("url") or raw.get("url"),
        "photo": (raw.get("photoUrls") or [None])[0] or vehicle.get("photoUrl"),
        "description": retail.get("description") or "",
        "_source": "auto.dev",
    }


def fetch_listings(cfg: dict) -> list[dict]:
    """Fetch + normalize listings for every configured model. Used cars only."""
    headers = _headers()
    want_used = cfg["search"].get("condition", "used").lower() == "used"
    seen_vins: set[str] = set()
    out: list[dict] = []

    for model in cfg["search"]["models"]:
        for page in range(1, MAX_PAGES + 1):
            params = _build_params(cfg, model, page)
            resp = requests.get(BASE_URL, headers=headers, params=params,
                                timeout=REQUEST_TIMEOUT)
            if resp.status_code == 429:
                time.sleep(2)
                continue
            resp.raise_for_status()
            body = resp.json()
            rows = body.get("data", []) or []
            if not rows:
                break

            for raw in rows:
                listing = _normalize(raw)
                vin = listing.get("vin")
                if not vin or vin in seen_vins:
                    continue
                # Hard filters that the API doesn't always enforce cleanly.
                if want_used and (listing.get("condition") or "").lower() == "new":
                    continue
                mileage = listing.get("mileage") or 0
                if mileage and mileage > cfg["search"]["mileage_max"]:
                    continue
                seen_vins.add(vin)
                out.append(listing)

            # No more pages
            if not body.get("links", {}).get("next"):
                break
            time.sleep(0.3)  # be polite, stay under rate limit

    return out
