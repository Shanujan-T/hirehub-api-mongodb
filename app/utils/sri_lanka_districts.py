"""Sri Lanka district cost-of-living multipliers for seeded CategoryPricing.

Tier constants (1.0 / 0.85 / 0.70 / 0.55) are the last-resort defaults when
Numbeo-backed multipliers are unavailable. Preferred values come from
``app/data/sri_lanka_col_index.json`` (written by
``app/scripts/fetch_district_col_index.py``), normalized so Colombo = 1.0.

These are transparent regional estimates for calibrating category base prices —
not verified category-specific market rates.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# district name → legacy tier (1–4) used only when Numbeo cache has no value
DISTRICT_TIERS: dict[str, int] = {
    # Tier 1 — highest
    "Colombo": 1,
    "Gampaha": 1,
    # Tier 2 — major urban
    "Kandy": 2,
    "Kalutara": 2,
    "Galle": 2,
    "Matara": 2,
    # Tier 3 — mid-size cities
    "Kurunegala": 3,
    "Anuradhapura": 3,
    "Ratnapura": 3,
    "Badulla": 3,
    "Jaffna": 3,
    "Puttalam": 3,
    "Matale": 3,
    "Hambantota": 3,
    # Tier 4 — rural / lower cost
    "Ampara": 4,
    "Batticaloa": 4,
    "Trincomalee": 4,
    "Nuwara Eliya": 4,
    "Kegalle": 4,
    "Polonnaruwa": 4,
    "Monaragala": 4,
    "Vavuniya": 4,
    "Mannar": 4,
    "Kilinochchi": 4,
    "Mullaitivu": 4,
}

TIER_MULTIPLIERS: dict[int, float] = {
    1: 1.0,
    2: 0.85,
    3: 0.70,
    4: 0.55,
}

# District → Numbeo first-level admin unit (province) name
DISTRICT_PROVINCE: dict[str, str] = {
    "Colombo": "Western Province",
    "Gampaha": "Western Province",
    "Kalutara": "Western Province",
    "Kandy": "Central Province",
    "Matale": "Central Province",
    "Nuwara Eliya": "Central Province",
    "Galle": "Southern Province",
    "Matara": "Southern Province",
    "Hambantota": "Southern Province",
    "Jaffna": "Northern Province",
    "Kilinochchi": "Northern Province",
    "Mannar": "Northern Province",
    "Vavuniya": "Northern Province",
    "Mullaitivu": "Northern Province",
    "Batticaloa": "Eastern Province",
    "Ampara": "Eastern Province",
    "Trincomalee": "Eastern Province",
    "Kurunegala": "North Western Province",
    "Puttalam": "North Western Province",
    "Anuradhapura": "North Central Province",
    "Polonnaruwa": "North Central Province",
    "Badulla": "Uva Province",
    "Monaragala": "Uva Province",
    "Ratnapura": "Sabaragamuwa Province",
    "Kegalle": "Sabaragamuwa Province",
}

SRI_LANKA_DISTRICTS: tuple[str, ...] = tuple(DISTRICT_TIERS.keys())

# Cities we attempt to scrape from Numbeo (skip ultra-thin rural districts).
NUMBEO_SCRAPE_CITIES: tuple[str, ...] = (
    "Colombo",
    "Gampaha",
    "Kandy",
    "Kalutara",
    "Galle",
    "Matara",
    "Kurunegala",
    "Anuradhapura",
    "Ratnapura",
    "Badulla",
    "Jaffna",
    "Puttalam",
    "Matale",
    "Hambantota",
    "Trincomalee",
    "Nuwara Eliya",
    "Kegalle",
    "Vavuniya",
)

COL_CACHE_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "sri_lanka_col_index.json"
)

_cached_multipliers: dict[str, float] | None = None
_cached_meta: dict[str, dict] | None = None


def district_tier(district: str) -> int | None:
    """Return tier 1–4 for a known district name (case-insensitive), else None."""
    if not district:
        return None
    key = district.strip().lower()
    for name, tier in DISTRICT_TIERS.items():
        if name.lower() == key:
            return tier
    return None


def tier_multiplier(tier: int) -> float:
    return TIER_MULTIPLIERS.get(int(tier), 1.0)


def _canonical_district(name: str) -> str | None:
    key = name.strip().lower()
    for district in SRI_LANKA_DISTRICTS:
        if district.lower() == key:
            return district
    return None


def load_col_cache(force_reload: bool = False) -> dict:
    """Load the Numbeo COL cache JSON (empty dict if missing/invalid)."""
    global _cached_multipliers, _cached_meta
    if force_reload:
        _cached_multipliers = None
        _cached_meta = None
    if not COL_CACHE_PATH.is_file():
        return {}
    try:
        with COL_CACHE_PATH.open(encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to read COL cache %s: %s", COL_CACHE_PATH, exc)
        return {}


def _ensure_multiplier_maps() -> None:
    global _cached_multipliers, _cached_meta
    if _cached_multipliers is not None and _cached_meta is not None:
        return
    data = load_col_cache()
    multipliers: dict[str, float] = {}
    meta: dict[str, dict] = {}
    districts = data.get("districts") or {}
    if isinstance(districts, dict):
        for name, row in districts.items():
            canonical = _canonical_district(str(name))
            if not canonical or not isinstance(row, dict):
                continue
            mult = row.get("multiplier")
            try:
                mult_f = float(mult)
            except (TypeError, ValueError):
                continue
            if mult_f <= 0:
                continue
            multipliers[canonical] = mult_f
            meta[canonical] = {
                "source": row.get("source") or "unknown",
                "index": row.get("index"),
                "contributors": row.get("contributors"),
            }
    _cached_multipliers = multipliers
    _cached_meta = meta


def reload_col_multipliers() -> None:
    """Clear in-memory COL multiplier cache (call after a successful fetch)."""
    global _cached_multipliers, _cached_meta
    _cached_multipliers = None
    _cached_meta = None
    _ensure_multiplier_maps()


def district_col_meta(district: str) -> dict | None:
    """Return audit metadata for a district multiplier, if cached."""
    _ensure_multiplier_maps()
    canonical = _canonical_district(district) if district else None
    if not canonical or _cached_meta is None:
        return None
    return _cached_meta.get(canonical)


def district_multiplier(district: str) -> float:
    """
    Cost-of-living multiplier for a district (Colombo reference = 1.0).

    Prefers Numbeo-backed cached values; falls back to legacy tier constants.
    """
    _ensure_multiplier_maps()
    canonical = _canonical_district(district) if district else None
    if canonical and _cached_multipliers and canonical in _cached_multipliers:
        return float(_cached_multipliers[canonical])
    tier = district_tier(canonical or district or "")
    if tier is None:
        return 1.0
    return tier_multiplier(tier)


def match_district(location: str | None) -> str | None:
    """
    Map a free-text job location to a canonical district name.

    Exact match first, then substring (e.g. "Colombo 07" → Colombo).
    """
    if not location or not str(location).strip():
        return None
    loc = str(location).strip().lower()
    for name in SRI_LANKA_DISTRICTS:
        if name.lower() == loc:
            return name
    # Prefer longer names first to avoid partial collisions
    for name in sorted(SRI_LANKA_DISTRICTS, key=len, reverse=True):
        if name.lower() in loc:
            return name
    return None
