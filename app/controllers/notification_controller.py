import logging

from flask import jsonify

from app.extensions import db
from app.models.notification_model import Notification
from app.utils import utc_now
from app.utils.notification_utils import deliver_notification

logger = logging.getLogger(__name__)


def create_notification(
    user_id,
    notification_type,
    title,
    message,
    related_entity_type=None,
    related_entity_id=None,
    link_href=None,
):
    """Create a notification for one user. Non-blocking; logs and returns None on failure."""
    if related_entity_type == "community_member" and related_entity_id and not link_href:
        link_href = f"/community-admin/my-community/pending/{related_entity_id}"
    return deliver_notification(
        user_id,
        notification_type=notification_type,
        title=title,
        body=message,
        link_href=link_href,
    )


def list_notifications(user_id, unread_only=False):
    query = Notification.query.filter_by(user_id=user_id)
    if unread_only:
        query = query.filter(Notification.read_at.is_(None))
    rows = query.order_by(Notification.created_at.desc()).limit(50).all()
    unread_count = Notification.query.filter_by(user_id=user_id, read_at=None).count()
    return jsonify({"notifications": [n.to_dict() for n in rows], "unread_count": unread_count}), 200


def unread_count(user_id):
    count = Notification.query.filter_by(user_id=user_id, read_at=None).count()
    return jsonify({"unread_count": count}), 200


def mark_read(notification_id, user_id):
    notification = Notification.query.filter_by(id=notification_id, user_id=user_id).first()
    if not notification:
        return jsonify({"error": "Notification not found."}), 404
    if not notification.read_at:
        notification.read_at = utc_now()
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            return jsonify({"error": "Failed to mark notification read."}), 500
    return jsonify({"notification": notification.to_dict()}), 200


def mark_all_read(user_id):
    try:
        Notification.query.filter_by(user_id=user_id, read_at=None).update(
            {"read_at": utc_now()},
            synchronize_session=False,
        )
        db.session.commit()
        return jsonify({"message": "All notifications marked read."}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Failed to mark notifications read."}), 500
