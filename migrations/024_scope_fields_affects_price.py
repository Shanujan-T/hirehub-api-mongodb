"""Annotate category scope_schema fields with affects_price + unit_size.

Migrates legacy baseline_unit-driven scaling (per_word / per_sqft / per_hour)
into the generic scope_fields format so pricing never hardcodes field names.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _annotate_field(field: dict, baseline_unit: str | None) -> dict:
    out = dict(field)
    if out.get("type") != "number":
        out["affects_price"] = False
        out.pop("unit_size", None)
        return out

    key = str(out.get("key") or "")
    unit = (baseline_unit or "").strip().lower()
    affects = bool(out["affects_price"]) if "affects_price" in out else False
    unit_size = out.get("unit_size", 1)

    # Preserve already-configured pricing fields; only fill gaps from legacy units.
    if not affects:
        if unit == "per_word" and key == "word_count":
            affects = True
            unit_size = out.get("unit_size") or 100
        elif unit == "per_sqft" and key in ("area_sqft", "square_feet"):
            affects = True
            unit_size = out.get("unit_size") or 1
        elif unit == "per_hour" and key in ("hours", "estimated_hours"):
            affects = True
            unit_size = out.get("unit_size") or 1
        elif key == "word_count":
            # Content Writing historically scaled on word_count even before flags existed.
            affects = True
            unit_size = out.get("unit_size") or 100

    try:
        unit_size_f = float(unit_size)
    except (TypeError, ValueError):
        unit_size_f = 1.0
    if unit_size_f <= 0:
        unit_size_f = 1.0

    out["affects_price"] = affects
    out["unit_size"] = int(unit_size_f) if unit_size_f == int(unit_size_f) else unit_size_f
    return out


def run_migration() -> None:
    from app import create_app
    from app.extensions import db
    from app.models.category_model import Category
    from app.utils.scope_utils import normalize_scope_schema

    app = create_app()
    with app.app_context():
        updated = 0
        for cat in Category.query.all():
            schema = cat.get_scope_schema()
            if not schema:
                continue
            annotated = [
                _annotate_field(f, getattr(cat, "baseline_unit", None)) for f in schema if isinstance(f, dict)
            ]
            normalized, errors = normalize_scope_schema(annotated)
            if errors:
                print(f"Skip {cat.name}: {errors}")
                continue
            before = json.dumps(schema, sort_keys=True)
            after = json.dumps(normalized or [], sort_keys=True)
            if before == after:
                continue
            cat.set_scope_schema(normalized)
            updated += 1
            print(
                f"Annotated scope_fields for {cat.name} "
                f"(pricing_unit={cat.pricing_unit()})"
            )
        db.session.commit()
        print(f"Migration complete: 024_scope_fields_affects_price (updated={updated}).")


if __name__ == "__main__":
    run_migration()
