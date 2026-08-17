"""Category scope_schema and job scope_data helpers."""

from __future__ import annotations

import json
import re
from typing import Any

ALLOWED_SCOPE_TYPES = frozenset({"number", "select", "multiselect", "text"})
_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def parse_json_value(raw: str | None) -> Any:
    if raw is None or raw == "":
        return None
    if isinstance(raw, (list, dict)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None


def dump_json_value(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def pricing_fields(schema: list[dict] | None) -> list[dict]:
    """Numeric scope fields that participate in price scaling."""
    if not schema:
        return []
    return [
        f
        for f in schema
        if isinstance(f, dict)
        and f.get("type") == "number"
        and bool(f.get("affects_price"))
    ]


def pricing_unit_from_schema(schema: list[dict] | None) -> str:
    """Return 'scaled' when any affects_price number field exists, else 'flat'."""
    return "scaled" if pricing_fields(schema) else "flat"


def normalize_scope_schema(raw: Any) -> tuple[list[dict] | None, list[str]]:
    """Validate and normalize a scope_schema / scope_fields payload. Empty/null clears schema."""
    errors: list[str] = []
    if raw is None or raw == "" or raw == []:
        return None, errors
    if isinstance(raw, str):
        raw = parse_json_value(raw)
    if not isinstance(raw, list):
        return None, ["scope_schema must be an array of field definitions."]

    normalized: list[dict] = []
    seen_keys: set[str] = set()
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            errors.append(f"scope_schema[{index}] must be an object.")
            continue
        key = str(item.get("key") or "").strip()
        label = str(item.get("label") or "").strip()
        field_type = str(item.get("type") or "").strip().lower()
        if not key:
            errors.append(f"scope_schema[{index}].key is required.")
            continue
        if not _KEY_RE.match(key):
            errors.append(
                f"scope_schema[{index}].key must be snake_case starting with a letter."
            )
            continue
        if key in seen_keys:
            errors.append(f"Duplicate scope_schema key: {key}.")
            continue
        seen_keys.add(key)
        if not label:
            errors.append(f"scope_schema[{index}].label is required.")
            continue
        if field_type not in ALLOWED_SCOPE_TYPES:
            errors.append(
                f"scope_schema[{index}].type must be one of: number, select, multiselect, text."
            )
            continue

        field: dict[str, Any] = {
            "key": key,
            "label": label,
            "type": field_type,
            "required": bool(item["required"]) if "required" in item else True,
        }
        unit = str(item.get("unit") or "").strip()
        if unit:
            field["unit"] = unit

        # Pricing participation — only meaningful for number fields.
        if field_type == "number":
            affects = item.get("affects_price")
            if affects is None:
                affects = False
            field["affects_price"] = bool(affects)
            unit_size_raw = item.get("unit_size", 1)
            try:
                unit_size = float(unit_size_raw)
            except (TypeError, ValueError):
                errors.append(f"scope_schema[{index}].unit_size must be a number.")
                continue
            if unit_size <= 0:
                errors.append(f"scope_schema[{index}].unit_size must be > 0.")
                continue
            # Prefer ints when whole numbers (e.g. per 100 words).
            field["unit_size"] = int(unit_size) if unit_size == int(unit_size) else unit_size
        else:
            field["affects_price"] = False

        if field_type in ("select", "multiselect"):
            options = item.get("options") or []
            if isinstance(options, str):
                options = [o.strip() for o in options.split(",") if o.strip()]
            if not isinstance(options, list) or not options:
                errors.append(
                    f"scope_schema[{index}].options is required for {field_type} fields."
                )
                continue
            cleaned = []
            for opt in options:
                text = str(opt).strip()
                if text and text not in cleaned:
                    cleaned.append(text)
            if not cleaned:
                errors.append(f"scope_schema[{index}].options must include valid values.")
                continue
            field["options"] = cleaned

        normalized.append(field)

    if errors:
        return None, errors
    return normalized or None, errors


def validate_scope_data(schema: list[dict] | None, raw_data: Any) -> tuple[dict | None, list[str]]:
    """Validate job scope_data against category schema. No schema → pass through empty."""
    if not schema:
        return None, []

    errors: list[str] = []
    if raw_data is None or raw_data == "":
        data: dict = {}
    elif isinstance(raw_data, str):
        parsed = parse_json_value(raw_data)
        if not isinstance(parsed, dict):
            return None, ["scope_data must be an object."]
        data = parsed
    elif isinstance(raw_data, dict):
        data = raw_data
    else:
        return None, ["scope_data must be an object."]

    cleaned: dict[str, Any] = {}
    schema_keys = {field["key"] for field in schema}

    for field in schema:
        key = field["key"]
        required = field.get("required", True)
        value = data.get(key, None)
        field_type = field["type"]

        if value is None or value == "" or value == []:
            if required:
                errors.append(f"scope_data.{key} ({field['label']}) is required.")
            continue

        if field_type == "number":
            try:
                number = float(value)
            except (TypeError, ValueError):
                errors.append(f"scope_data.{key} must be a number.")
                continue
            if number <= 0:
                errors.append(f"scope_data.{key} must be greater than 0.")
                continue
            cleaned[key] = int(number) if number == int(number) else number
        elif field_type == "text":
            text = str(value).strip()
            if not text:
                if required:
                    errors.append(f"scope_data.{key} ({field['label']}) is required.")
                continue
            cleaned[key] = text
        elif field_type == "select":
            text = str(value).strip()
            options = field.get("options") or []
            if text not in options:
                errors.append(f"scope_data.{key} must be one of the allowed options.")
                continue
            cleaned[key] = text
        elif field_type == "multiselect":
            if isinstance(value, str):
                values = [v.strip() for v in value.split(",") if v.strip()]
            elif isinstance(value, list):
                values = [str(v).strip() for v in value if str(v).strip()]
            else:
                errors.append(f"scope_data.{key} must be a list of selected options.")
                continue
            options = set(field.get("options") or [])
            invalid = [v for v in values if v not in options]
            if invalid:
                errors.append(f"scope_data.{key} contains invalid options: {', '.join(invalid)}.")
                continue
            # Preserve order, unique
            unique: list[str] = []
            for v in values:
                if v not in unique:
                    unique.append(v)
            if required and not unique:
                errors.append(f"scope_data.{key} ({field['label']}) is required.")
                continue
            cleaned[key] = unique

    # Ignore unknown keys silently (forward-compatible)
    _ = [k for k in data.keys() if k not in schema_keys]

    if errors:
        return None, errors
    return cleaned, errors


def format_scope_display(schema: list[dict] | None, scope_data: dict | None) -> list[dict]:
    """Return labeled rows for UI: [{label, value, key}]."""
    if not schema or not scope_data:
        return []
    rows = []
    for field in schema:
        key = field["key"]
        if key not in scope_data:
            continue
        value = scope_data[key]
        unit = field.get("unit") or ""
        if field["type"] == "multiselect" and isinstance(value, list):
            display = ", ".join(str(v) for v in value)
        elif field["type"] == "number":
            display = f"{value}{(' ' + unit) if unit else ''}".strip()
        else:
            display = str(value)
            if unit:
                display = f"{display} {unit}".strip()
        rows.append({"key": key, "label": field["label"], "value": display})
    return rows


def format_unit_phrase(field: dict) -> str:
    """Human-readable 'per 100 words' / 'per sq ft' style phrase for captions."""
    label = str(field.get("label") or field.get("key") or "unit").strip()
    unit = str(field.get("unit") or "").strip()
    try:
        unit_size = float(field.get("unit_size") or 1)
    except (TypeError, ValueError):
        unit_size = 1.0
    if unit_size == int(unit_size):
        size_disp = str(int(unit_size))
    else:
        size_disp = str(unit_size)

    # Prefer short unit when present ("sq ft"), else lowercased label ("word count" → words-ish).
    if unit:
        noun = unit
    else:
        noun = label.lower()
        # Mild plural tidy: "Word count" → "words" if it ends with "count"
        if noun.endswith(" count"):
            noun = noun[: -len(" count")].strip() + "s"
        elif noun.endswith("y") and not noun.endswith(("ay", "ey", "oy", "uy")):
            noun = noun[:-1] + "ies"

    if unit_size == 1:
        return f"per {noun}"
    return f"per {size_disp} {noun}"
