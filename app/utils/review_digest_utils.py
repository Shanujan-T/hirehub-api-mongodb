"""AI review digest cache helpers — regenerate on review create (like category pricing)."""

from __future__ import annotations

import json
import logging

from app.extensions import db
from app.models.ai_review_digest_model import AiReviewDigest
from app.models.review_model import Review
from app.utils import utc_now
from app.utils.ai_client import ask_ai

logger = logging.getLogger(__name__)

MIN_REVIEWS_FOR_DIGEST = 3


def _parse_digest_json(text: str | None) -> dict | None:
    if not text:
        return None
    import re

    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None


def _normalize_phrases(items, limit: int = 4) -> list[str]:
    if not isinstance(items, list):
        return []
    out = []
    for item in items:
        phrase = str(item or "").strip()
        if phrase and phrase not in out:
            out.append(phrase[:80])
        if len(out) >= limit:
            break
    return out


def recalc_review_digest(community_id: int) -> AiReviewDigest | None:
    """Rebuild cached digest for a community after a new review (event-driven)."""
    reviews = (
        Review.query.filter_by(community_id=community_id)
        .order_by(Review.created_at.desc())
        .limit(40)
        .all()
    )
    review_count = len(reviews)
    if review_count < MIN_REVIEWS_FOR_DIGEST:
        existing = AiReviewDigest.query.filter_by(community_id=community_id).first()
        if existing:
            db.session.delete(existing)
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
        return None

    comments = []
    for review in reviews:
        comment = (review.comment or "").strip()
        if comment:
            comments.append(f"[{review.rating}/5] {comment[:220]}")
        else:
            comments.append(f"[{review.rating}/5] (no written comment)")

    raw = ask_ai(
        system_prompt=(
            "You summarize community review themes for a public profile. "
            "Reply with a single JSON object only — no markdown. Schema: "
            '{"praised":["short phrase",...],"flagged":["short phrase",...]}. '
            "Use 2-4 short phrases per list (not full sentences). "
            "praised = recurring strengths; flagged = recurring concerns. "
            "Stay neutral and fair. No blame language."
        ),
        user_prompt="Reviews:\n" + "\n".join(comments[:30]) + "\nReturn JSON only.",
        max_tokens=250,
    )
    parsed = _parse_digest_json(raw)
    praised = _normalize_phrases((parsed or {}).get("praised"))
    flagged = _normalize_phrases((parsed or {}).get("flagged"))
    if not praised and not flagged:
        logger.warning("recalc_review_digest: AI returned empty for community_id=%s", community_id)
        return AiReviewDigest.query.filter_by(community_id=community_id).first()

    row = AiReviewDigest.query.filter_by(community_id=community_id).first()
    payload_praised = json.dumps(praised)
    payload_flagged = json.dumps(flagged)
    if row:
        row.praised_json = payload_praised
        row.flagged_json = payload_flagged
        row.review_count = review_count
        row.updated_at = utc_now()
    else:
        row = AiReviewDigest(
            community_id=community_id,
            praised_json=payload_praised,
            flagged_json=payload_flagged,
            review_count=review_count,
            updated_at=utc_now(),
        )
        db.session.add(row)

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception("recalc_review_digest failed to save community_id=%s", community_id)
        return None
    return row


def get_review_digest(community_id: int) -> dict:
    """Return cached digest or an unavailable/insufficient payload."""
    count = Review.query.filter_by(community_id=community_id).count()
    if count < MIN_REVIEWS_FOR_DIGEST:
        return {
            "available": False,
            "reason": "insufficient_reviews",
            "review_count": count,
            "praised": [],
            "flagged": [],
        }

    row = AiReviewDigest.query.filter_by(community_id=community_id).first()
    if not row:
        row = recalc_review_digest(community_id)
    if not row:
        return {
            "available": False,
            "reason": "ai_unavailable",
            "review_count": count,
            "praised": [],
            "flagged": [],
        }
    return row.to_dict()
