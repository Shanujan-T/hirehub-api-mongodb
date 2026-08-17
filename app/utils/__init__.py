from datetime import datetime, timezone


def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def title_case_words(value: str | None) -> str:
    """Capitalize each whitespace-separated word (e.g. 'fan repair' → 'Fan Repair')."""
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    return " ".join(
        part[:1].upper() + part[1:].lower() if part else "" for part in text.split()
    )
