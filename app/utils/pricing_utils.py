from __future__ import annotations

from decimal import Decimal
from datetime import date, datetime
import json
import logging
import os
from statistics import mean

import requests
from sqlalchemy import func

from app.extensions import db
from app.models.category_model import Category
from app.models.category_pricing_model import CategoryPricing
from app.models.contract_model import Contract
from app.models.job_model import Job
from app.models.pricing_reference_model import PricingReference
from app.utils import utc_now
from app.utils.scope_utils import (
    format_unit_phrase,
    parse_json_value,
    pricing_fields,
)
from app.utils.sri_lanka_districts import (
    DISTRICT_TIERS,
    district_multiplier,
    match_district,
)

# Minimum samples before a data-backed tier is used.
MIN_SAMPLES = 3
_TEST_DATA_MARKERS = ("test", "dummy", "sample", "demo", "fake", "lorem ipsum")
logger = logging.getLogger(__name__)
BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
WEB_SEARCH_TIMEOUT_SECONDS = 8
ANTHROPIC_TIMEOUT_SECONDS = 12
WEB_FALLBACK_RESULT_COUNT = 5


def recalc_category_pricing(category_id, location):
    """Recalculate average price for a category + location from completed contracts.

    When real samples exist, clears is_seeded_estimate so seeded rows never win again.
    """
    result = (
        db.session.query(
            func.avg(Contract.total_amount),
            func.count(Contract.id),
        )
        .join(Contract.job)
        .filter(
            Contract.status == "completed",
            Contract.job.has(category_id=category_id, location=location),
        )
        .first()
    )

    avg_price = result[0] if result and result[0] else Decimal("0")
    sample_size = result[1] if result else 0

    pricing = CategoryPricing.query.filter_by(
        category_id=category_id, location=location
    ).first()

    if pricing:
        pricing.average_price = avg_price or Decimal("0")
        pricing.sample_size = sample_size
        pricing.last_updated = utc_now()
        if sample_size > 0:
            pricing.is_seeded_estimate = False
    else:
        pricing = CategoryPricing(
            category_id=category_id,
            location=location,
            average_price=avg_price or Decimal("0"),
            sample_size=sample_size,
            is_seeded_estimate=False if sample_size > 0 else True,
            last_updated=utc_now(),
        )
        db.session.add(pricing)

    db.session.commit()
    return pricing


def seed_district_pricing(category_id: int | None = None) -> dict:
    """
    Seed/update CategoryPricing for all 25 districts from category.baseline_price.

    - Uses Colombo baseline × district cost-of-living multiplier
      (Numbeo-backed cache when available, else legacy tier constants).
    - Never overwrites rows with sample_size > 0 (real contract data).
    - Only refreshes rows still flagged is_seeded_estimate (or missing rows).
    """
    if category_id is not None:
        categories = Category.query.filter_by(id=int(category_id)).all()
    else:
        categories = Category.query.filter_by(status="approved").all()

    created = updated = skipped = 0
    for cat in categories:
        if cat.baseline_price is None:
            skipped += 1
            continue
        base = float(cat.baseline_price)
        for district in DISTRICT_TIERS:
            price = round(base * district_multiplier(district), 2)
            row = CategoryPricing.query.filter_by(
                category_id=cat.id, location=district
            ).first()
            if row:
                # Never overwrite real accumulated contract data
                if row.sample_size and int(row.sample_size) > 0:
                    skipped += 1
                    continue
                row.average_price = price
                row.sample_size = 0
                row.is_seeded_estimate = True
                row.last_updated = utc_now()
                updated += 1
            else:
                db.session.add(
                    CategoryPricing(
                        category_id=cat.id,
                        location=district,
                        average_price=price,
                        sample_size=0,
                        is_seeded_estimate=True,
                        last_updated=utc_now(),
                    )
                )
                created += 1

    db.session.commit()
    return {"created": created, "updated": updated, "skipped": skipped}


def _float_or_none(value) -> float | None:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    if n != n:  # NaN
        return None
    return n


# ---------------------------------------------------------------------------
# Generic scope-based scaling (driven by category.scope_schema / scope_fields).
# Never hardcode field names like word_count / area_sqft here.
# ---------------------------------------------------------------------------


def scale_price(base_rate: float, scope_data: dict, scope_key: str | None) -> float:
    if scope_key and scope_data:
        try:
            val = float(scope_data.get(scope_key))
            if val > 0:
                return base_rate * val
        except (TypeError, ValueError):
            pass
    return base_rate


def _schema_for(category: Category | None, scope_schema=None) -> list:
    if isinstance(scope_schema, list):
        return scope_schema
    if category is not None:
        schema = category.get_scope_schema()
        if isinstance(schema, list):
            return schema
    return []


def _unit_scope_provided(category: Category | None, scope_data: dict, schema=None) -> bool:
    """True when baseline_scope_key numeric scope value was supplied."""
    if not category or not category.baseline_scope_key:
        return False
    val = _float_or_none(scope_data.get(category.baseline_scope_key))
    return val is not None and val > 0


def _baseline_estimate(category: Category | None, scope_data: dict, schema=None) -> float | None:
    """Scale category.baseline_price by baseline_scope_key key when present."""
    if not category or category.baseline_price is None:
        return None
    baseline = float(category.baseline_price)
    return round(scale_price(baseline, scope_data, category.baseline_scope_key), 2)


def _scale_reference_price(
    reference: float, category: Category | None, scope_data: dict, schema=None
) -> float:
    """Apply baseline_scope_key scaling to a district/base reference price."""
    scope_key = category.baseline_scope_key if category else None
    return round(scale_price(float(reference), scope_data, scope_key), 2)


def _baseline_note(category: Category | None, scope_data: dict | None = None, schema=None) -> str:
    if not category or not category.baseline_scope_key:
        return "Estimated (no local data yet)"
    schema = _schema_for(category, schema)
    field = next((f for f in schema if isinstance(f, dict) and f.get("key") == category.baseline_scope_key), None)
    if field:
        return f"Estimated from category baseline ({format_unit_phrase(field)})"
    return "Estimated (no local data yet)"


def _completed_jobs_with_amounts(category_id: int, location: str) -> list[tuple[Job, float]]:
    """Tier 1 source: completed contracts for category + location."""
    rows = (
        db.session.query(Job, Contract.total_amount)
        .join(Contract, Contract.job_id == Job.id)
        .filter(
            Contract.status == "completed",
            Job.category_id == category_id,
            Job.location == location,
            Contract.total_amount.isnot(None),
        )
        .all()
    )
    out: list[tuple[Job, float]] = []
    for job, amount in rows:
        if _is_test_or_dummy_job(job):
            continue
        try:
            out.append((job, float(amount)))
        except (TypeError, ValueError):
            continue
    return out


def _is_test_or_dummy_job(job: Job) -> bool:
    """Keep explicitly non-production jobs out of pricing samples."""
    text = f"{job.title or ''} {job.description or ''}".lower()
    return any(marker in text for marker in _TEST_DATA_MARKERS)


def _missing_required_scope_fields(schema: list, scope_data: dict) -> list[str]:
    missing = []
    for field in schema:
        if not isinstance(field, dict) or not field.get("required", True):
            continue
        value = scope_data.get(field.get("key"))
        # Explicitly check empty values rather than truthiness: numeric zero is
        # supplied input and must not be mistaken for an omitted field.
        if value is None or (isinstance(value, str) and not value.strip()) or value == []:
            missing.append(str(field.get("label") or field.get("key")))
    return missing


def _round_lkr(value: float) -> float:
    return round(value / 50.0) * 50.0


def _reference_price(row: PricingReference, district: str | None) -> float:
    prices = row.get_district_prices()
    if district and prices.get(district) is not None:
        return float(prices[district])
    return float(row.base_price)


def _has_dataset_category(category: Category) -> bool:
    """True when this category is covered by the imported pricing CSV."""
    return db.session.query(
        PricingReference.id
    ).filter(
        func.lower(PricingReference.category) == category.name.lower()
    ).first() is not None


def _scope_summary(scope_data: dict, schema: list) -> str:
    """Create a compact, readable scope phrase for a local-price web search."""
    labels = {
        str(field.get("key")): str(field.get("label") or field.get("key"))
        for field in schema
        if isinstance(field, dict) and field.get("key")
    }
    parts = []
    for key, value in scope_data.items():
        if value is None or value == "" or value == []:
            continue
        display = ", ".join(map(str, value)) if isinstance(value, list) else str(value)
        parts.append(f"{labels.get(str(key), key)}: {display}")
    return "; ".join(parts)


def _brave_price_search(query: str) -> list[dict] | None:
    """Return a small, safe subset of Brave web results for price extraction."""
    api_key = os.getenv("BRAVE_SEARCH_API_KEY", "").strip()
    if not api_key:
        logger.warning("[suggested-price] web fallback unavailable: BRAVE_SEARCH_API_KEY is not configured")
        return None
    try:
        response = requests.get(
            BRAVE_SEARCH_URL,
            params={"q": query, "count": WEB_FALLBACK_RESULT_COUNT, "search_lang": "en"},
            headers={"Accept": "application/json", "X-Subscription-Token": api_key},
            timeout=WEB_SEARCH_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        raw_results = response.json().get("web", {}).get("results", [])
        results = [
            {
                "title": str(item.get("title") or "")[:300],
                "description": str(item.get("description") or "")[:800],
                "url": str(item.get("url") or "")[:500],
            }
            for item in raw_results[:WEB_FALLBACK_RESULT_COUNT]
            if isinstance(item, dict)
        ]
        logger.info("[suggested-price] Brave fallback search completed query=%r result_count=%s", query, len(results))
        return results
    except (requests.RequestException, ValueError) as exc:
        logger.exception("[suggested-price] Brave fallback search failed query=%r error=%s", query, exc)
        return None


def _extract_web_price_range(category: Category, location: str, scope: str, results: list[dict]) -> tuple[float, float] | None:
    """Ask Haiku to extract—not invent—a local LKR range from search snippets."""
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        logger.warning("[suggested-price] web fallback unavailable: ANTHROPIC_API_KEY is not configured")
        return None

    prompt = (
        "Extract a rough local service price range only from the supplied search results. "
        "The request is for a service in Sri Lanka. Reject results for another country, unrelated "
        "services, and non-pricing content. Do not use outside knowledge and do not guess. "
        "Return exactly one JSON object with this schema: "
        '{"status":"ok","low_lkr":number,"high_lkr":number} or '
        '{"status":"insufficient_data"}. Values must be LKR, positive, and low_lkr <= high_lkr.\n\n'
        f"Category: {category.name}\nLocation: {location}\nScope: {scope or 'Not specified'}\n"
        f"Search results:\n{json.dumps(results, ensure_ascii=False)}"
    )
    try:
        response = requests.post(
            ANTHROPIC_MESSAGES_URL,
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": os.getenv("ANTHROPIC_HAIKU_MODEL", "claude-haiku-4-5-20251001"),
                "max_tokens": 150,
                "temperature": 0,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=ANTHROPIC_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        content = response.json().get("content", [])
        text = next(
            (block.get("text") for block in content if isinstance(block, dict) and block.get("type") == "text"),
            "",
        )
        extracted = json.loads(text)
        if extracted.get("status") != "ok":
            logger.info("[suggested-price] Haiku fallback found insufficient local price data category=%s", category.name)
            return None
        low = float(extracted["low_lkr"])
        high = float(extracted["high_lkr"])
        if low <= 0 or high <= 0 or low > high:
            raise ValueError("Haiku returned an invalid LKR range")
        return _round_lkr(low), _round_lkr(high)
    except (requests.RequestException, ValueError, TypeError, KeyError, AttributeError, json.JSONDecodeError) as exc:
        logger.exception("[suggested-price] Haiku fallback extraction failed category=%s error=%s", category.name, exc)
        return None


def _web_fallback_suggestion(category: Category, location: str, scope_data: dict, schema: list) -> dict:
    """Low-confidence fallback exclusively for categories absent from the CSV."""
    scope = _scope_summary(scope_data, schema)
    query = " ".join(part for part in (category.name, scope, "service price", location, "Sri Lanka") if part).strip()
    logger.info("[suggested-price] method=web_fallback category=%s query=%r", category.name, query)
    results = _brave_price_search(query)
    if not results:
        return _result(None, 0, "web_fallback_unavailable", "Price estimate unavailable for this category.")
    price_range = _extract_web_price_range(category, location, scope, results)
    if price_range is None:
        return _result(None, 0, "web_fallback_unavailable", "Price estimate unavailable for this category.")
    low, high = price_range
    midpoint = _round_lkr((low + high) / 2)
    result = _result(
        midpoint,
        0,
        "web_fallback",
        "Estimated from web sources (limited local data available).",
        is_seeded_estimate=False,
    )
    result["suggested_price_low"] = low
    result["suggested_price_high"] = high
    return result


def _dataset_suggestion(category: Category, location: str, scope_data: dict, schema: list) -> dict | None:
    """Use the imported CSV as the primary, scope-aware price reference."""
    rows = (
        PricingReference.query.filter(func.lower(PricingReference.category) == category.name.lower())
        .order_by(PricingReference.quantity.asc())
        .all()
    )
    if not rows:
        logger.warning("[suggested-price] CSV lookup found no category rows", extra={"category": category.name, "location": location})
        return None

    district = match_district(location)
    numeric_field = next(
        (field for field in schema if isinstance(field, dict) and field.get("key") == category.baseline_scope_key and field.get("type") == "number"),
        None,
    ) or next((field for field in schema if isinstance(field, dict) and field.get("type") == "number"), None)

    if numeric_field:
        requested = _float_or_none(scope_data.get(numeric_field.get("key")))
        if requested is None or requested < 0:
            logger.warning(
                "[suggested-price] CSV lookup skipped: numeric scope is missing or negative category=%s field=%s value=%s",
                category.name, numeric_field.get("key"), requested,
            )
            return None
        unit = str(numeric_field.get("unit") or "").strip().lower()
        tier_rows = [row for row in rows if not unit or row.unit.strip().lower() == unit] or rows
        tier_rows = sorted(tier_rows, key=lambda row: row.quantity)
        logger.info(
            "[suggested-price] CSV matching rows category=%s requested=%s unit=%s rows=%s",
            category.name, requested, unit,
            [(row.scope, row.quantity, _reference_price(row, district)) for row in tier_rows],
        )
        exact = next((row for row in tier_rows if row.quantity == requested), None)
        if exact:
            price = _round_lkr(_reference_price(exact, district))
            return _result(price, 0, "dataset_reference", f"CSV reference: {exact.scope} in {district or location}.", is_seeded_estimate=True)

        lower = max((row for row in tier_rows if row.quantity < requested), key=lambda row: row.quantity, default=None)
        upper = min((row for row in tier_rows if row.quantity > requested), key=lambda row: row.quantity, default=None)
        if lower and upper:
            lower_price = _reference_price(lower, district)
            upper_price = _reference_price(upper, district)
            fraction = (requested - lower.quantity) / (upper.quantity - lower.quantity)
            price = _round_lkr(lower_price + fraction * (upper_price - lower_price))
            logger.info("[suggested-price] CSV interpolation requested=%s lower=%s upper=%s price=%s", requested, lower.scope, upper.scope, price)
            result = _result(price, 0, "dataset_interpolated_range", f"CSV reference interpolated between {lower.scope} and {upper.scope} in {district or location}.", is_seeded_estimate=True)
            result["suggested_price_low"] = _round_lkr(min(lower_price, upper_price))
            result["suggested_price_high"] = _round_lkr(max(lower_price, upper_price))
            return result

        # Do not scale a short request down below the dataset's smallest valid scope tier.
        nearest = tier_rows[0] if requested < tier_rows[0].quantity else tier_rows[-1]
        price = _round_lkr(_reference_price(nearest, district))
        logger.info("[suggested-price] CSV nearest-tier fallback requested=%s selected=%s price=%s", requested, nearest.scope, price)
        return _result(price, 0, "dataset_reference", f"CSV reference: nearest scope tier {nearest.scope} in {district or location}.", is_seeded_estimate=True)

    selected_text = " ".join(str(value) for value in scope_data.values() if isinstance(value, str)).strip().lower()
    chosen = next((row for row in rows if selected_text and (selected_text in row.scope.lower() or row.scope.lower() in selected_text)), rows[0])
    price = _round_lkr(_reference_price(chosen, district))
    return _result(price, 0, "dataset_reference", f"CSV reference: {chosen.scope} in {district or location}.", is_seeded_estimate=True)


def _blend_valid_completed_history(reference: dict, category_id: int, location: str, scope_data: dict, scope_key: str | None) -> dict:
    """Apply a deliberately small secondary adjustment from valid completed contracts."""
    history = _completed_jobs_with_amounts(category_id, location)
    if len(history) < MIN_SAMPLES or not reference.get("suggested_price"):
        return reference

    requested_qty = _float_or_none(scope_data.get(scope_key)) if scope_key else None
    comparable = []
    for job, amount in history:
        job_qty = _float_or_none((job.get_scope_data() or {}).get(scope_key)) if scope_key else None
        if requested_qty and job_qty and job_qty > 0:
            comparable.append(amount / job_qty * requested_qty)
        elif not requested_qty:
            comparable.append(amount)
    if len(comparable) < MIN_SAMPLES:
        return reference

    dataset_price = float(reference["suggested_price"])
    blended = _round_lkr(dataset_price * 0.85 + mean(comparable) * 0.15)
    factor = blended / dataset_price if dataset_price else 1.0
    reference["suggested_price"] = blended
    reference["average_price"] = blended
    reference["sample_size"] = len(comparable)
    reference["note"] += f" Gently adjusted using {len(comparable)} valid completed contracts."
    for key in ("suggested_price_low", "suggested_price_high"):
        if key in reference:
            reference[key] = _round_lkr(float(reference[key]) * factor)
    return reference


def _apply_deadline_urgency(reference: dict, deadline: str | None) -> dict | None:
    """Apply a transparent, fixed rush premium to a completed CSV suggestion."""
    try:
        deadline_text = str(deadline or "").strip()
        try:
            due_date = date.fromisoformat(deadline_text)
        except ValueError:
            due_date = datetime.strptime(deadline_text, "%m/%d/%Y").date()
    except (TypeError, ValueError):
        logger.exception("[suggested-price] deadline parsing failed for value=%r", deadline)
        return None

    days_until_due = (due_date - date.today()).days
    logger.info("[suggested-price] deadline urgency deadline=%r parsed_date=%s days_until_due=%s", deadline, due_date.isoformat(), days_until_due)
    if days_until_due < 0:
        return None
    if days_until_due < 2:
        multiplier, label = 1.30, "high urgency (+30%, due within 48 hours)"
    elif days_until_due < 7:
        multiplier, label = 1.15, "moderate urgency (+15%, due within 7 days)"
    else:
        multiplier, label = 1.00, "standard timeline (no rush premium)"

    for key in ("suggested_price", "average_price", "suggested_price_low", "suggested_price_high"):
        if reference.get(key) is not None:
            reference[key] = _round_lkr(float(reference[key]) * multiplier)
    reference["urgency"] = {"days_until_due": days_until_due, "multiplier": multiplier, "label": label}
    reference["note"] = f"{reference.get('note', '').rstrip('.')} Deadline: {label}."
    return reference


def _posted_jobs_with_prices(
    category_id: int, location: str, exclude_job_id: int | None = None
) -> list[tuple[Job, float]]:
    """Tier 2 source: all posted jobs' asking prices (final_price), any status."""
    q = Job.query.filter(
        Job.category_id == category_id,
        Job.location == location,
        Job.final_price.isnot(None),
    )
    if exclude_job_id is not None:
        q = q.filter(Job.id != exclude_job_id)
    out: list[tuple[Job, float]] = []
    for job in q.all():
        try:
            price = float(job.final_price)
        except (TypeError, ValueError):
            continue
        if price < 0:
            continue
        out.append((job, price))
    return out


def _multiselect_delta(
    history: list[tuple[Job, float]], field_key: str, selected: list[str]
) -> tuple[float, int]:
    """Sum with-vs-without average deltas for selected features with enough data."""
    total_delta = 0.0
    adjusted_features = 0
    for feature in selected:
        with_prices: list[float] = []
        without_prices: list[float] = []
        for job, amount in history:
            data = job.get_scope_data() or {}
            features = data.get(field_key) or []
            if isinstance(features, str):
                features = [features]
            if not isinstance(features, list):
                continue
            if feature in features:
                with_prices.append(amount)
            else:
                without_prices.append(amount)
        if len(with_prices) >= MIN_SAMPLES and len(without_prices) >= MIN_SAMPLES:
            total_delta += mean(with_prices) - mean(without_prices)
            adjusted_features += 1
    return total_delta, adjusted_features


def _result(price, sample_size, method, note, *, is_seeded_estimate: bool = False):
    return {
        "suggested_price": price,
        "average_price": price,
        "sample_size": sample_size,
        "method": method,
        "note": note,
        "is_seeded_estimate": bool(is_seeded_estimate),
    }


def _lookup_district_pricing(category_id: int, location: str | None):
    """Return (CategoryPricing|None, canonical_district|None)."""
    district = match_district(location)
    if not district:
        return None, None
    row = CategoryPricing.query.filter_by(
        category_id=category_id, location=district
    ).first()
    return row, district


def _apply_scope_to_history(
    history: list[tuple[Job, float]],
    schema: list,
    scope_data: dict,
    scope_key: str | None,
    *,
    flat_method: str,
    allow_multiselect: bool,
) -> dict | None:
    """
    Build a suggestion from job+amount pairs.

    Returns None if there are fewer than MIN_SAMPLES rows.
    Scope-adjusted numeric (and optionally multiselect) refinements apply when possible;
    otherwise the flat mean is used.
    """
    if len(history) < MIN_SAMPLES:
        return None

    sample_size = len(history)
    suggested = round(mean(amount for _, amount in history), 2)
    used_scope = False

    if flat_method == "historical_average":
        note = (
            f"Based on {sample_size} completed job"
            f"{'s' if sample_size != 1 else ''} in this area."
        )
    else:
        note = (
            f"Based on {sample_size} similar job posting"
            f"{'s' if sample_size != 1 else ''} (asking prices, not yet completed)."
        )

    if schema and scope_data:
        if scope_key and scope_data:
            field = next((f for f in schema if isinstance(f, dict) and f.get("key") == scope_key), None)
            if field and field.get("type") == "number":
                ppus: list[float] = []
                for job, amount in history:
                    job_val = _float_or_none((job.get_scope_data() or {}).get(scope_key))
                    if job_val and job_val > 0:
                        ppus.append(amount / job_val)
                if len(ppus) >= MIN_SAMPLES:
                    current_val = _float_or_none(scope_data.get(scope_key))
                    if current_val and current_val > 0:
                        avg_ppu = mean(ppus)
                        suggested = round(scale_price(avg_ppu, scope_data, scope_key), 2)
                        sample_size = len(ppus)
                        used_scope = True
                        unit_bit = f" ({format_unit_phrase(field)})"
                        if flat_method == "historical_average":
                            note = (
                                f"Based on {sample_size} completed jobs in this area "
                                f"(size-adjusted{unit_bit})."
                            )
                        else:
                            note = (
                                f"Based on {sample_size} similar job postings "
                                f"(asking prices, size-adjusted{unit_bit})."
                            )

        if allow_multiselect:
            for field in schema:
                if field.get("type") != "multiselect":
                    continue
                key = field.get("key")
                if not key or key not in scope_data:
                    continue
                selected = scope_data[key]
                if isinstance(selected, str):
                    selected = [selected]
                if not isinstance(selected, list) or not selected:
                    continue
                delta, adjusted = _multiselect_delta(
                    history, key, [str(s) for s in selected]
                )
                if adjusted:
                    suggested = round(float(suggested) + delta, 2)
                    used_scope = True
                    note = (
                        f"Based on {sample_size} completed jobs in this area "
                        "(feature-adjusted)."
                    )

    if used_scope and flat_method == "historical_average":
        method = "scope_adjusted"
    else:
        method = flat_method

    return _result(suggested, sample_size, method, note)


def get_pricing_suggestion(
    category_id,
    location,
    scope_data=None,
    scope_schema=None,
    exclude_job_id=None,
    deadline=None,
):
    """
    Suggest a price for category + location.

    Order:
      1. CategoryPricing with real samples (sample_size > 0) for matched district
      2. Completed contracts (3+) → historical_average / scope_adjusted
      3. Posted jobs' final_price (3+) → posted_jobs_average
      4. Seeded CategoryPricing estimate for district (is_seeded_estimate)
      5. category.baseline_price (Tier-1 Colombo reference)
      6. insufficient_data
    """
    category = Category.query.get(category_id)

    if isinstance(scope_data, str):
        scope_data = parse_json_value(scope_data)
    if not isinstance(scope_data, dict):
        scope_data = {}

    schema = scope_schema
    if isinstance(schema, str):
        schema = parse_json_value(schema)
    if schema is None and category is not None:
        schema = category.get_scope_schema()
    if not isinstance(schema, list):
        schema = []

    scope_key = category.baseline_scope_key if category else None

    logger.info(
        "[suggested-price] function input category_id=%s category=%s location=%r deadline=%r scope_data=%s required_scope_fields=%s",
        category_id,
        category.name if category else None,
        location,
        deadline,
        scope_data,
        [
            {"key": field.get("key"), "label": field.get("label"), "type": field.get("type"), "value": scope_data.get(field.get("key"))}
            for field in schema
            if isinstance(field, dict) and field.get("required", True)
        ],
    )

    if category:
        if not deadline:
            return _result(None, 0, "deadline_required", "Select a valid deadline to see a price suggestion.")
        missing_scope = _missing_required_scope_fields(schema, scope_data)
        logger.info("[suggested-price] required-scope validation missing=%s", missing_scope)
        if missing_scope:
            return _result(
                None,
                0,
                "scope_required",
                "Select job scope to see a price suggestion: " + ", ".join(missing_scope) + ".",
            )

        csv_covered = _has_dataset_category(category)
        logger.info("[suggested-price] category=%s method=csv csv_covered=%s", category.name, csv_covered)
        dataset = _dataset_suggestion(category, location, scope_data, schema) if csv_covered else None
        if dataset is not None:
            dataset = _blend_valid_completed_history(
                dataset, category.id, location, scope_data, scope_key
            )
            adjusted = _apply_deadline_urgency(dataset, deadline)
            if adjusted is not None:
                logger.info("[suggested-price] method=csv category=%s", category.name)
                return adjusted
            return _result(None, 0, "deadline_required", "Select a valid future deadline to see a price suggestion.")
        if not csv_covered:
            return _web_fallback_suggestion(category, location, scope_data, schema)

        # CSV coverage is authoritative. A covered category must never trigger
        # paid web/LLM calls merely because its scoped lookup was unusable.
        return _result(None, 0, "csv_unavailable", "Price estimate unavailable for this category.")

    pricing_row, district = _lookup_district_pricing(category_id, location)

    # --- District table: real accumulated data ---
    if pricing_row and pricing_row.sample_size and pricing_row.sample_size > 0:
        scaled = _scale_reference_price(
            float(pricing_row.average_price), category, scope_data, schema
        )
        note = (
            f"Estimated from local completed contracts"
            + (f" in {district}" if district else "")
        )
        if category and category.baseline_scope_key:
            val = _float_or_none(scope_data.get(category.baseline_scope_key))
            if val is not None and val > 0:
                field = next((f for f in schema if isinstance(f, dict) and f.get("key") == category.baseline_scope_key), None)
                if field:
                    note = f"{note} ({format_unit_phrase(field)})"
        return _result(
            scaled,
            int(pricing_row.sample_size),
            "historical_average",
            note + ".",
            is_seeded_estimate=False,
        )

    # --- Live completed contracts ---
    completed = _completed_jobs_with_amounts(category_id, location)
    tier1 = _apply_scope_to_history(
        completed,
        schema,
        scope_data,
        scope_key,
        flat_method="historical_average",
        allow_multiselect=True,
    )
    if tier1 is not None:
        if (
            tier1.get("method") != "scope_adjusted"
            and _unit_scope_provided(category, scope_data, schema)
        ):
            baseline = _baseline_estimate(category, scope_data, schema)
            if baseline is not None:
                return _result(
                    baseline,
                    0,
                    "baseline_estimate",
                    _baseline_note(category, scope_data, schema),
                    is_seeded_estimate=True,
                )
        tier1["is_seeded_estimate"] = False
        if not tier1.get("note"):
            tier1["note"] = "Estimated from local completed contracts"
        return tier1

    # --- Live posted jobs ---
    posted = _posted_jobs_with_prices(category_id, location, exclude_job_id=exclude_job_id)
    tier2 = _apply_scope_to_history(
        posted,
        schema,
        scope_data,
        scope_key,
        flat_method="posted_jobs_average",
        allow_multiselect=False,
    )
    if tier2 is not None:
        if (
            tier2.get("method") != "scope_adjusted"
            and _unit_scope_provided(category, scope_data, schema)
        ):
            baseline = _baseline_estimate(category, scope_data, schema)
            if baseline is not None:
                return _result(
                    baseline,
                    0,
                    "baseline_estimate",
                    _baseline_note(category, scope_data, schema),
                    is_seeded_estimate=True,
                )
        tier2["is_seeded_estimate"] = False
        return tier2

    # --- Seeded district estimate (sample_size == 0 rows are estimates) ---
    if pricing_row and (
        pricing_row.is_seeded_estimate or not (pricing_row.sample_size or 0)
    ):
        scaled = _scale_reference_price(
            float(pricing_row.average_price), category, scope_data, schema
        )
        note = "Estimated (regional baseline — no completed contracts yet)"
        if category and category.baseline_scope_key:
            val = _float_or_none(scope_data.get(category.baseline_scope_key))
            if val is not None and val > 0:
                field = next((f for f in schema if isinstance(f, dict) and f.get("key") == category.baseline_scope_key), None)
                if field:
                    note = (
                        f"Estimated (regional baseline — no completed contracts yet; "
                        f"{format_unit_phrase(field)})"
                    )
        return _result(
            scaled,
            0,
            "seeded_district_estimate",
            note,
            is_seeded_estimate=True,
        )

    # --- Tier-1 Colombo / category base ---
    baseline = _baseline_estimate(category, scope_data, schema)
    if baseline is not None:
        note = _baseline_note(category, scope_data, schema)
        if not category or not category.baseline_scope_key:
            note = "Estimated (no local data yet)"
        return _result(
            baseline,
            0,
            "baseline_estimate",
            note,
            is_seeded_estimate=True,
        )

    return _result(
        None,
        0,
        "insufficient_data",
        "No pricing data for this category + location yet.",
        is_seeded_estimate=False,
    )


def suggest_price(category: str, quantity: float | int, district: str, scope: str | None = None) -> int | None:
    from app.models.pricing_reference_model import PricingReference
    from sqlalchemy import func

    # 1. Fetch all PricingReference rows for category, sorted by quantity
    rows = (
        PricingReference.query.filter(func.lower(PricingReference.category) == func.lower(category))
        .order_by(PricingReference.quantity.asc())
        .all()
    )
    if not rows:
        return None

    requested_qty = quantity
    try:
        requested_qty = float(quantity)
        if requested_qty.is_integer():
            requested_qty = int(requested_qty)
    except (TypeError, ValueError):
        requested_qty = 1

    # 2. Check if a row's quantity exactly matches requested quantity
    exact_match = next((r for r in rows if r.quantity == requested_qty), None)
    
    is_quantity_scaled = len([r for r in rows if r.quantity > 1]) > 1

    base_price = None

    if is_quantity_scaled:
        if exact_match:
            base_price = float(exact_match.base_price)
        elif requested_qty > rows[-1].quantity:
            # Extrapolate using highest tier's rate
            highest_tier = rows[-1]
            rate = float(highest_tier.base_price) / highest_tier.quantity
            base_price = rate * requested_qty
        elif requested_qty < rows[0].quantity:
            # Below lowest tier: extrapolate using lowest tier's rate
            lowest_tier = rows[0]
            rate = float(lowest_tier.base_price) / lowest_tier.quantity
            base_price = rate * requested_qty
        else:
            # Interpolate
            lower_tier = max((r for r in rows if r.quantity < requested_qty), key=lambda r: r.quantity)
            upper_tier = min((r for r in rows if r.quantity > requested_qty), key=lambda r: r.quantity)
            rate_lower = float(lower_tier.base_price) / lower_tier.quantity
            rate_upper = float(upper_tier.base_price) / upper_tier.quantity
            
            # Linear interpolation of per-unit rate
            t = (requested_qty - lower_tier.quantity) / (upper_tier.quantity - lower_tier.quantity)
            rate = rate_lower + t * (rate_upper - rate_lower)
            base_price = rate * requested_qty
    else:
        # Flat one-off category
        matched_row = None
        cleaned_req_scope = str(scope or "").strip().lower()
        if cleaned_req_scope:
            # 1. Try exact match first
            matched_row = next((r for r in rows if r.scope.strip().lower() == cleaned_req_scope), None)
            # 2. Try substring match
            if not matched_row:
                matched_row = next(
                    (r for r in rows if cleaned_req_scope in r.scope.strip().lower() or r.scope.strip().lower() in cleaned_req_scope),
                    None
                )
            # 3. Try word prefix sharing (prefix of length >= 3)
            if not matched_row:
                def get_prefixes(text_str):
                    return [w[:4] for w in text_str.lower().split() if len(w) >= 3]
                
                req_prefixes = get_prefixes(cleaned_req_scope)
                for r in rows:
                    row_prefixes = get_prefixes(r.scope)
                    if any(p in row_prefixes for p in req_prefixes):
                        matched_row = r
                        break
        
        if not matched_row:
            # Match closest scope tier by quantity
            matched_row = min(rows, key=lambda r: abs(r.quantity - requested_qty))

        base_price = float(matched_row.base_price)

    # 3. Apply location multiplier
    LOCATION_MULTIPLIERS = {
        "colombo": 1.30,
        "gampaha": 1.20,
        "kandy": 1.15,
        "kalutara": 1.10,
        "galle": 1.10,
        "matara": 1.05,
        "jaffna": 1.05,
        "kurunegala": 1.00,
        "anuradhapura": 0.95,
        "badulla": 0.95
    }
    
    district_norm = str(district or "").strip().lower()
    multiplier = LOCATION_MULTIPLIERS.get(district_norm, 1.00)
    final_price = base_price * multiplier

    # 4. Round to the nearest 50 LKR
    rounded_price = round(final_price / 50.0) * 50
    return int(rounded_price)

