"""Shared OpenRouter (OpenAI-compatible) helper for HireHub AI features."""

from __future__ import annotations

import logging
import os
import threading
import time

logger = logging.getLogger(__name__)

# OpenRouter auto-router: picks an available free model.
_MODEL = "openrouter/free"
_OPENROUTER_BASE = "https://openrouter.ai/api/v1"

# Per-user, per-feature cooldown to protect free-tier caps (~20 req/min, 50/day).
_DEFAULT_COOLDOWN_SECONDS = 8.0
_lock = threading.Lock()
_last_call: dict[tuple[int, str], float] = {}
_authentication_disabled = False


def is_ai_configured() -> bool:
    return bool(os.getenv("OPENROUTER_API_KEY", "").strip()) and not _authentication_disabled


def _is_authentication_error(exc: Exception) -> bool:
    """Return true for a credential failure that cannot succeed until configuration changes."""
    return getattr(exc, "status_code", None) in (401, 403)


def _disable_after_authentication_error(exc: Exception) -> None:
    """Stop retrying a rejected OpenRouter credential for the current process."""
    global _authentication_disabled
    with _lock:
        _authentication_disabled = True
    logger.warning(
        "OpenRouter authentication failed (status=%s). AI features are disabled for this "
        "server process; replace OPENROUTER_API_KEY and restart the API.",
        getattr(exc, "status_code", "unknown"),
    )


def check_ai_cooldown(
    user_id: int,
    feature: str,
    cooldown_seconds: float = _DEFAULT_COOLDOWN_SECONDS,
) -> tuple[bool, int]:
    """Return (allowed, retry_after_seconds)."""
    key = (int(user_id), feature)
    now = time.monotonic()
    with _lock:
        last = _last_call.get(key)
        if last is None:
            return True, 0
        elapsed = now - last
        if elapsed >= cooldown_seconds:
            return True, 0
        return False, max(1, int(cooldown_seconds - elapsed) + 1)


def mark_ai_call(user_id: int, feature: str) -> None:
    with _lock:
        _last_call[(int(user_id), feature)] = time.monotonic()


def cooldown_response(retry_after: int):
    """Flask-ready JSON body + status for AI cooldown."""
    from flask import jsonify

    return (
        jsonify(
            {
                "error": f"AI is cooling down — try again in {retry_after}s.",
                "retry_after": retry_after,
                "available": False,
            }
        ),
        429,
    )


def _openrouter_client():
    from openai import OpenAI

    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key or _authentication_disabled:
        return None
    return OpenAI(
        base_url=_OPENROUTER_BASE,
        api_key=api_key,
        default_headers={
            "HTTP-Referer": os.getenv("OPENROUTER_HTTP_REFERER", "https://hirehub.app"),
            "X-Title": os.getenv("OPENROUTER_APP_TITLE", "HireHub"),
        },
    )


def _extract_text(completion) -> str | None:
    choice = completion.choices[0] if completion and completion.choices else None
    content = getattr(getattr(choice, "message", None), "content", None) if choice else None
    if isinstance(content, str):
        result = content.strip()
        return result or None
    return None


def ask_ai(system_prompt: str, user_prompt: str, max_tokens: int = 500) -> str | None:
    """Call OpenRouter free-tier chat and return plain text, or None on any failure."""
    client = _openrouter_client()
    if not client:
        logger.info("ask_ai unavailable: OPENROUTER_API_KEY is not configured or has been disabled")
        return None

    try:
        completion = client.chat.completions.create(
            model=_MODEL,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return _extract_text(completion)
    except Exception as exc:
        if _is_authentication_error(exc):
            _disable_after_authentication_error(exc)
            return None
        logger.exception("ask_ai failed")
        return None


def ask_ai_with_image(
    system_prompt: str,
    user_prompt: str,
    image_url: str,
    max_tokens: int = 500,
) -> str | None:
    """Best-effort vision call via OpenRouter free router. Returns None if unavailable."""
    client = _openrouter_client()
    if not client:
        logger.info("ask_ai_with_image unavailable: OpenRouter is not configured or has been disabled")
        return None
    if not image_url:
        return None

    try:
        completion = client.chat.completions.create(
            model=_MODEL,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                },
            ],
        )
        return _extract_text(completion)
    except Exception as exc:
        if _is_authentication_error(exc):
            _disable_after_authentication_error(exc)
            return None
        # Free-tier often has no vision-capable model — degrade silently.
        logger.info("ask_ai_with_image unavailable or failed (vision best-effort): %s", exc)
        return None


# Back-compat alias during migration (prefer ask_ai).
ask_claude = ask_ai
