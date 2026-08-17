"""
Fetch Sri Lanka cost-of-living indices from Numbeo via Apify, cache them, and
derive per-district multipliers (Colombo = 1.0) for the pricing engine.

Usage (from hirehub-api-02, with APIFY_TOKEN set):

    PYTHONPATH=. python -m app.scripts.fetch_district_col_index
    PYTHONPATH=. python -m app.scripts.fetch_district_col_index --skip-fetch   # rebuild multipliers from cache only
    PYTHONPATH=. python -m app.scripts.fetch_district_col_index --reseed       # also re-seed CategoryPricing

Env:
    APIFY_TOKEN              required for live fetches
    APIFY_NUMBEO_ACTOR       default: automation-lab/numbeo-scraper
    NUMBEO_MIN_CONTRIBUTORS  default: 10
    APIFY_CITY_BATCH_PAUSE_S pause between per-city runs (default: 2)

On Apify/network failure the previous cache file is kept intact.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

# Allow `python -m app.scripts.fetch_district_col_index` from repo root / api root
_API_ROOT = Path(__file__).resolve().parents[2]
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from dotenv import load_dotenv

load_dotenv(_API_ROOT / ".env")

from app.utils.sri_lanka_districts import (  # noqa: E402
    COL_CACHE_PATH,
    DISTRICT_PROVINCE,
    DISTRICT_TIERS,
    NUMBEO_SCRAPE_CITIES,
    SRI_LANKA_DISTRICTS,
    TIER_MULTIPLIERS,
    reload_col_multipliers,
)

logger = logging.getLogger("fetch_district_col_index")

DEFAULT_ACTOR = "automation-lab/numbeo-scraper"
MIN_CONTRIBUTORS_DEFAULT = 10

# Basket items used to build a relative COL proxy when rankings omit a city.
_BASKET_ITEM_HINTS = (
    "meal, inexpensive restaurant",
    "milk (regular), (1 liter)",
    "loaf of fresh white bread",
    "eggs (regular) (12)",
    "rice (white), (1kg)",
    "potato (1kg)",
    "one-way ticket (local transport)",
    "gasoline (1 liter)",
    "basic (electricity, heating, cooling, water, garbage)",
    "internet (",
    "apartment (1 bedroom) outside of centre",
    "apartment (1 bedroom) outside of city centre",
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _min_contributors() -> int:
    try:
        return max(1, int(os.getenv("NUMBEO_MIN_CONTRIBUTORS", MIN_CONTRIBUTORS_DEFAULT)))
    except ValueError:
        return MIN_CONTRIBUTORS_DEFAULT


def _float_or_none(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        n = float(value)
        return None if n != n else n
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "")
        try:
            n = float(cleaned)
        except ValueError:
            return None
        return None if n != n else n
    return None


def _int_or_none(value: Any) -> int | None:
    n = _float_or_none(value)
    if n is None:
        return None
    return int(n)


def _pick_index(item: dict) -> float | None:
    """Extract Cost of Living Index (prefer plain COL over COL+Rent)."""
    for key in (
        "costOfLivingIndex",
        "cost_of_living_index",
        "Cost of Living Index",
        "colIndex",
        "coli",
    ):
        val = _float_or_none(item.get(key))
        if val is not None and val > 0:
            return val
    for key in (
        "costOfLivingPlusRentIndex",
        "cost_of_living_plus_rent_index",
        "Cost of Living Plus Rent Index",
        "colPlusRentIndex",
    ):
        val = _float_or_none(item.get(key))
        if val is not None and val > 0:
            return val
    return None


def _pick_contributors(item: dict) -> int | None:
    for key in (
        "contributors",
        "contributorCount",
        "contributorsCount",
        "numContributors",
        "dataPoints",
        "entries",
        "sampleSize",
    ):
        val = _int_or_none(item.get(key))
        if val is not None and val >= 0:
            return val
    # Nested / text blobs sometimes include "91 contributors"
    for key, value in item.items():
        if not isinstance(value, str):
            continue
        if "contributor" not in key.lower() and "contributor" not in value.lower():
            continue
        m = re.search(r"(\d+)\s*contributor", value, re.I)
        if m:
            return int(m.group(1))
    return None


def _normalize_city_label(label: str) -> str | None:
    """Map Apify/Numbeo city labels onto our district names when possible."""
    if not label:
        return None
    raw = label.strip()
    # Rankings often use "Colombo, Sri Lanka"
    city_part = raw.split(",")[0].strip()
    lower = city_part.lower()
    aliases = {
        "dehiwala-mount lavinia": "Colombo",
        "dehiwala": "Colombo",
        "mount lavinia": "Colombo",
        "negombo": "Gampaha",
        "moratuwa": "Colombo",
        "sri jayawardenepura kotte": "Colombo",
        "kotte": "Colombo",
    }
    if lower in aliases:
        return aliases[lower]
    for district in SRI_LANKA_DISTRICTS:
        if district.lower() == lower:
            return district
    return None


def _is_sri_lanka_item(item: dict) -> bool:
    country = str(item.get("country") or "").strip().lower()
    if country in {"sri lanka", "lk"}:
        return True
    city = str(item.get("city") or "")
    if "sri lanka" in city.lower():
        return True
    return False


def load_cache() -> dict:
    if not COL_CACHE_PATH.is_file():
        return {}
    try:
        with COL_CACHE_PATH.open(encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read existing cache: %s", exc)
        return {}


def save_cache(payload: dict) -> Path:
    COL_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = COL_CACHE_PATH.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    tmp.replace(COL_CACHE_PATH)
    return COL_CACHE_PATH


def _get_apify_client():
    token = (os.getenv("APIFY_TOKEN") or "").strip()
    if not token:
        raise RuntimeError(
            "APIFY_TOKEN is not set. Add it to hirehub-api-02/.env to fetch Numbeo data."
        )
    try:
        from apify_client import ApifyClient
    except ImportError as exc:
        raise RuntimeError(
            "apify-client is not installed. Run: pip install apify-client"
        ) from exc
    return ApifyClient(token)


def _run_actor(client, run_input: dict) -> list[dict]:
    actor_id = (os.getenv("APIFY_NUMBEO_ACTOR") or DEFAULT_ACTOR).strip()
    logger.info("Calling Apify actor %s with %s", actor_id, run_input)
    run = client.actor(actor_id).call(run_input=run_input)
    if not run or not run.get("defaultDatasetId"):
        logger.warning("Actor run returned no dataset: %s", run)
        return []
    items: list[dict] = []
    for item in client.dataset(run["defaultDatasetId"]).iterate_items():
        if isinstance(item, dict):
            items.append(item)
    logger.info("Actor returned %s items", len(items))
    return items


def fetch_rankings_sri_lanka(client) -> dict[str, dict]:
    """Pull global rankings once and keep Sri Lanka rows (indexes + optional contributors)."""
    try:
        items = _run_actor(
            client,
            {
                "mode": "rankings",
                # Free tier may truncate; we still harvest whatever SL cities appear.
                "maxCities": 0,
            },
        )
    except Exception:
        logger.exception("Rankings fetch failed")
        return {}

    out: dict[str, dict] = {}
    for item in items:
        city_label = str(item.get("city") or "")
        district = _normalize_city_label(city_label)
        if not district:
            continue
        if not (
            _is_sri_lanka_item(item)
            or "sri lanka" in city_label.lower()
            or district in SRI_LANKA_DISTRICTS
        ):
            continue
        index = _pick_index(item)
        if index is None:
            continue
        out[district] = {
            "cost_of_living_index": index,
            "contributors": _pick_contributors(item),
            "raw_city": item.get("city"),
            "via": "rankings",
        }
    return out


def _basket_score(items: list[dict]) -> float | None:
    prices: list[float] = []
    for item in items:
        name = str(
            item.get("item")
            or item.get("itemName")
            or item.get("name")
            or ""
        ).strip().lower()
        if not name:
            continue
        if not any(hint in name for hint in _BASKET_ITEM_HINTS):
            continue
        price = _float_or_none(
            item.get("price")
            if item.get("price") is not None
            else item.get("avgPrice")
        )
        if price is not None and price > 0:
            prices.append(price)
    if len(prices) < 3:
        return None
    return float(mean(prices))


def fetch_city_batch(client, city: str) -> dict | None:
    """Scrape one city (free-tier friendly: one city per actor run)."""
    try:
        items = _run_actor(
            client,
            {
                "mode": "city_prices",
                "cities": [city],
            },
        )
    except Exception:
        logger.exception("City fetch failed for %s", city)
        return None

    if not items:
        return None

    # Prefer an explicit index if the actor included one on any row.
    index = None
    contributors = None
    for item in items:
        if index is None:
            index = _pick_index(item)
        if contributors is None:
            contributors = _pick_contributors(item)

    basket = _basket_score(items)
    return {
        "cost_of_living_index": index,
        "basket_score": basket,
        "contributors": contributors,
        "item_count": len(items),
        "via": "city_prices",
    }


def fetch_country_national(client) -> dict | None:
    """Best-effort national Sri Lanka signal via country price scrape / rankings."""
    # Try country prices through logiover-compatible input; automation-lab may ignore.
    try:
        items = _run_actor(
            client,
            {
                "mode": "city_prices",
                "cities": ["Sri Lanka"],
            },
        )
    except Exception:
        logger.exception("National fetch failed")
        return None
    if not items:
        return None
    index = None
    contributors = None
    for item in items:
        if index is None:
            index = _pick_index(item)
        if contributors is None:
            contributors = _pick_contributors(item)
    basket = _basket_score(items)
    return {
        "cost_of_living_index": index,
        "basket_score": basket,
        "contributors": contributors,
        "via": "national",
    }


def _merge_city_records(
    rankings: dict[str, dict],
    city_batches: dict[str, dict],
) -> dict[str, dict]:
    merged: dict[str, dict] = {}
    for city in NUMBEO_SCRAPE_CITIES:
        row: dict[str, Any] = {"city": city}
        if city in rankings:
            row.update(rankings[city])
        if city in city_batches:
            batch = city_batches[city]
            # Rankings index wins; fill gaps from city batch.
            if row.get("cost_of_living_index") is None:
                row["cost_of_living_index"] = batch.get("cost_of_living_index")
            if row.get("contributors") is None:
                row["contributors"] = batch.get("contributors")
            row["basket_score"] = batch.get("basket_score")
            row["item_count"] = batch.get("item_count")
            row["via"] = batch.get("via") or row.get("via")
        if (
            row.get("cost_of_living_index") is not None
            or row.get("basket_score") is not None
        ):
            merged[city] = row
    return merged


def _absolute_index_for_city(
    row: dict,
    colombo_basket: float | None,
    colombo_index: float | None,
) -> float | None:
    """Resolve a comparable absolute index number for a city row."""
    idx = _float_or_none(row.get("cost_of_living_index"))
    if idx is not None and idx > 0:
        return idx
    basket = _float_or_none(row.get("basket_score"))
    if (
        basket is not None
        and basket > 0
        and colombo_basket
        and colombo_basket > 0
        and colombo_index
        and colombo_index > 0
    ):
        # Scale basket ratio onto Colombo's official index units.
        return colombo_index * (basket / colombo_basket)
    return None


def _province_indices_from_cities(
    city_rows: dict[str, dict],
    min_contrib: int,
    colombo_basket: float | None,
    colombo_index: float | None,
) -> dict[str, dict]:
    buckets: dict[str, list[tuple[float, int | None]]] = {}
    for city, row in city_rows.items():
        province = DISTRICT_PROVINCE.get(city)
        if not province:
            continue
        contributors = _int_or_none(row.get("contributors"))
        if contributors is not None and contributors < min_contrib:
            continue
        index = _absolute_index_for_city(row, colombo_basket, colombo_index)
        if index is None:
            continue
        buckets.setdefault(province, []).append((index, contributors))

    out: dict[str, dict] = {}
    for province, pairs in buckets.items():
        idxs = [p[0] for p in pairs]
        contribs = [p[1] for p in pairs if p[1] is not None]
        out[province] = {
            "cost_of_living_index": float(mean(idxs)),
            "contributors": sum(contribs) if contribs else None,
            "city_count": len(pairs),
            "via": "province_aggregate_from_cities",
        }
    return out


def build_district_multipliers(
    city_rows: dict[str, dict],
    province_rows: dict[str, dict],
    national_index: float | None,
    min_contrib: int,
) -> tuple[dict[str, dict], float]:
    """
    Build per-district multiplier rows with auditable source labels.

    Sources (priority):
      city-level → province-level → national-fallback → tier-estimate
    """
    colombo_row = city_rows.get("Colombo") or {}
    colombo_basket = _float_or_none(colombo_row.get("basket_score"))
    colombo_index = _absolute_index_for_city(
        colombo_row, colombo_basket, _float_or_none(colombo_row.get("cost_of_living_index"))
    )
    # If Colombo only has a basket, treat basket as the reference index (=100 scale).
    if colombo_index is None and colombo_basket:
        colombo_index = colombo_basket

    if colombo_index is None or colombo_index <= 0:
        # Last resort: keep Colombo at 1.0 via synthetic index.
        colombo_index = 100.0
        logger.warning(
            "No Colombo COL index available; using synthetic 100.0 so multipliers stay defined."
        )

    districts: dict[str, dict] = {}
    for district in SRI_LANKA_DISTRICTS:
        city_row = city_rows.get(district)
        province = DISTRICT_PROVINCE.get(district)
        source = "tier-estimate"
        index: float | None = None
        contributors: int | None = None

        if city_row:
            contributors = _int_or_none(city_row.get("contributors"))
            city_index = _absolute_index_for_city(
                city_row, colombo_basket, colombo_index
            )
            reliable = contributors is None or contributors >= min_contrib
            # Unknown contributor count from rankings: still trust the index.
            if city_index is not None and reliable:
                index = city_index
                source = "city-level"
            elif city_index is not None and not reliable:
                logger.info(
                    "%s city index ignored (contributors=%s < %s); trying province",
                    district,
                    contributors,
                    min_contrib,
                )

        if index is None and province and province in province_rows:
            prow = province_rows[province]
            index = _float_or_none(prow.get("cost_of_living_index"))
            contributors = _int_or_none(prow.get("contributors"))
            if index is not None:
                source = "province-level"

        if index is None and national_index is not None and national_index > 0:
            index = national_index
            source = "national-fallback"
            contributors = None

        if index is None or index <= 0:
            tier = DISTRICT_TIERS[district]
            multiplier = float(TIER_MULTIPLIERS[tier])
            districts[district] = {
                "index": None,
                "multiplier": round(multiplier, 4),
                "source": "tier-estimate",
                "contributors": None,
                "province": province,
                "note": "No Numbeo city/province/national signal; legacy tier used.",
            }
            logger.info("%s → tier-estimate (tier %s → %s)", district, tier, multiplier)
            continue

        multiplier = float(index) / float(colombo_index)
        # Keep outliers from breaking admin base prices.
        multiplier = max(0.40, min(1.20, multiplier))
        districts[district] = {
            "index": round(float(index), 4),
            "multiplier": round(multiplier, 4),
            "source": source,
            "contributors": contributors,
            "province": province,
        }
        logger.info(
            "%s → multiplier=%.4f source=%s index=%.4f contributors=%s",
            district,
            multiplier,
            source,
            index,
            contributors,
        )

    # Force Colombo reference exactly 1.0
    if "Colombo" in districts:
        districts["Colombo"]["multiplier"] = 1.0

    return districts, float(colombo_index)


def fetch_and_build(*, skip_fetch: bool = False) -> dict:
    """Fetch (unless skip_fetch) and write the COL cache. Returns the payload."""
    previous = load_cache()
    min_contrib = _min_contributors()
    pause = float(os.getenv("APIFY_CITY_BATCH_PAUSE_S", "2") or 2)

    city_rows: dict[str, dict] = {}
    province_rows: dict[str, dict] = {}
    national_index: float | None = None
    fetch_errors: list[str] = []

    if skip_fetch:
        logger.info("Skipping Apify fetch; rebuilding multipliers from existing cache raw data.")
        city_rows = dict(previous.get("cities") or {})
        province_rows = dict(previous.get("provinces") or {})
        national_index = _float_or_none(
            (previous.get("national") or {}).get("cost_of_living_index")
        )
    else:
        try:
            client = _get_apify_client()
        except RuntimeError as exc:
            logger.error("%s", exc)
            if previous.get("districts"):
                logger.warning("Keeping last successful COL cache.")
                return previous
            raise

        rankings: dict[str, dict] = {}
        try:
            rankings = fetch_rankings_sri_lanka(client)
        except Exception as exc:
            fetch_errors.append(f"rankings: {exc}")
            logger.exception("Rankings failed; continuing with per-city batches")

        city_batches: dict[str, dict] = {}
        for i, city in enumerate(NUMBEO_SCRAPE_CITIES):
            # Skip re-fetch when rankings already gave a solid index + contributors
            existing = rankings.get(city)
            if (
                existing
                and existing.get("cost_of_living_index") is not None
                and (
                    existing.get("contributors") is None
                    or int(existing["contributors"]) >= min_contrib
                )
            ):
                logger.info("Using rankings data for %s; skipping city batch", city)
                continue
            logger.info("Fetching city batch %s/%s: %s", i + 1, len(NUMBEO_SCRAPE_CITIES), city)
            result = fetch_city_batch(client, city)
            if result:
                city_batches[city] = result
            else:
                fetch_errors.append(f"city:{city}")
            if pause > 0 and i < len(NUMBEO_SCRAPE_CITIES) - 1:
                time.sleep(pause)

        city_rows = _merge_city_records(rankings, city_batches)

        # If live fetch produced nothing, keep previous cache.
        if not city_rows:
            logger.error("No city COL data retrieved from Apify.")
            if previous.get("districts"):
                logger.warning("Falling back to last successful cached multipliers.")
                return previous
            # Still build tier-only payload so seed never sees null multipliers.
            city_rows = {}

        national = None
        try:
            national = fetch_country_national(client)
        except Exception as exc:
            fetch_errors.append(f"national: {exc}")

        colombo = city_rows.get("Colombo") or {}
        colombo_basket = _float_or_none(colombo.get("basket_score"))
        colombo_index_hint = _float_or_none(colombo.get("cost_of_living_index"))

        if national:
            national_index = _absolute_index_for_city(
                national, colombo_basket, colombo_index_hint
            )
            if national_index is None:
                national_index = _float_or_none(national.get("basket_score"))

        # If national still missing, average reliable city indexes.
        if national_index is None and city_rows:
            reliable = []
            for row in city_rows.values():
                contrib = _int_or_none(row.get("contributors"))
                if contrib is not None and contrib < min_contrib:
                    continue
                idx = _absolute_index_for_city(row, colombo_basket, colombo_index_hint)
                if idx is not None:
                    reliable.append(idx)
            if reliable:
                national_index = float(mean(reliable))

        province_rows = _province_indices_from_cities(
            city_rows, min_contrib, colombo_basket, colombo_index_hint
        )

    districts, colombo_index = build_district_multipliers(
        city_rows, province_rows, national_index, min_contrib
    )

    payload = {
        "fetched_at": _utc_now_iso(),
        "source": "numbeo_via_apify",
        "attribution": "Cost of living indices derived from Numbeo (https://www.numbeo.com).",
        "actor": (os.getenv("APIFY_NUMBEO_ACTOR") or DEFAULT_ACTOR).strip(),
        "min_contributors": min_contrib,
        "colombo_index": round(colombo_index, 4),
        "national": {
            "cost_of_living_index": round(national_index, 4) if national_index else None,
        },
        "cities": city_rows,
        "provinces": province_rows,
        "districts": districts,
        "fetch_errors": fetch_errors,
        "notes": [
            "Multipliers are district_index / colombo_index (Colombo forced to 1.0).",
            "city-level requires contributors >= min_contributors when a count is present.",
            "province-level is the mean of reliable city indexes in that province.",
            "tier-estimate uses the legacy 1.0/0.85/0.70/0.55 bands when Numbeo has no signal.",
        ],
    }
    path = save_cache(payload)
    reload_col_multipliers()
    logger.info("Wrote COL cache to %s (%s districts)", path, len(districts))
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-fetch",
        action="store_true",
        help="Rebuild district multipliers from the existing cache without calling Apify.",
    )
    parser.add_argument(
        "--reseed",
        action="store_true",
        help="After updating the cache, re-run seed_district_pricing() for all categories.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Debug logging.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        payload = fetch_and_build(skip_fetch=args.skip_fetch)
    except Exception:
        logger.exception("COL fetch failed")
        return 1

    # Summarise sources for audit
    sources: dict[str, int] = {}
    for row in (payload.get("districts") or {}).values():
        src = str((row or {}).get("source") or "unknown")
        sources[src] = sources.get(src, 0) + 1
    logger.info("District source breakdown: %s", sources)

    if args.reseed:
        from app import create_app
        from app.utils.pricing_utils import seed_district_pricing

        app = create_app()
        with app.app_context():
            stats = seed_district_pricing()
            logger.info("seed_district_pricing: %s", stats)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
