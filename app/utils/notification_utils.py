"""Persist and push in-app notifications to individual users."""

import logging

from app.extensions import db, socketio
from app.models.community_member_model import CommunityMember
from app.models.job_model import Job
from app.models.notification_model import Notification

logger = logging.getLogger(__name__)


def user_room(user_id: int) -> str:
    return f"user_{user_id}"


def get_community_admin_user_ids(community_id: int) -> list[int]:
    admins = CommunityMember.query.filter_by(
        community_id=community_id, role="admin", status="approved"
    ).all()
    if not admins:
        admins = (
            CommunityMember.query.filter_by(community_id=community_id, role="admin")
            .order_by(CommunityMember.id.asc())
            .all()
        )
    admin_ids = [m.user_id for m in admins]
    logger.info(
        "community_admin_lookup community_id=%s approved_admins=%s fallback_admins=%s admin_user_ids=%s",
        community_id,
        [
            {"membership_id": m.id, "user_id": m.user_id, "role": m.role, "status": m.status}
            for m in CommunityMember.query.filter_by(
                community_id=community_id, role="admin", status="approved"
            ).all()
        ],
        [
            {"membership_id": m.id, "user_id": m.user_id, "role": m.role, "status": m.status}
            for m in admins
        ],
        admin_ids,
    )
    return admin_ids


def deliver_notification(
    user_id: int,
    *,
    notification_type: str,
    title: str,
    body: str,
    link_href: str | None = None,
) -> Notification | None:
    """Insert a notification row and emit it over Socket.IO to the recipient."""
    if not user_id:
        return None
    try:
        notification = Notification(
            user_id=user_id,
            type=notification_type,
            title=title,
            body=body,
            link_href=link_href,
        )
        db.session.add(notification)
        db.session.commit()
        payload = notification.to_dict()
        socketio.emit("notification", payload, room=user_room(user_id))
        return notification
    except Exception:
        logger.exception(
            "Failed to deliver notification type=%s to user_id=%s",
            notification_type,
            user_id,
        )
        db.session.rollback()
        return None


def deliver_to_users(user_ids, **kwargs) -> None:
    seen: set[int] = set()
    for user_id in user_ids:
        if user_id and user_id not in seen:
            seen.add(user_id)
            deliver_notification(user_id, **kwargs)


def notify_community_admins(community_id: int, **kwargs) -> None:
    deliver_to_users(get_community_admin_user_ids(community_id), **kwargs)


def notify_community_join_request(
    community_id: int,
    membership_id: int,
    requester_name: str,
    community_name: str,
    requester_user_id: int,
) -> None:
    """Notify community admin(s) — never the requester."""
    requester_user_id = int(requester_user_id)
    admin_ids = [
        uid
        for uid in get_community_admin_user_ids(community_id)
        if uid != requester_user_id
    ]
    if not admin_ids:
        logger.warning(
            "NO ADMIN FOUND to notify for join request community_id=%s membership_id=%s requester_user_id=%s",
            community_id,
            membership_id,
            requester_user_id,
        )
        return

    logger.info(
        "Creating community_join_request notifications community_id=%s membership_id=%s recipient_user_ids=%s",
        community_id,
        membership_id,
        admin_ids,
    )
    for admin_user_id in admin_ids:
        try:
            result = deliver_notification(
                admin_user_id,
                notification_type="community_join_request",
                title="New join request",
                body=f"{requester_name} requested to join {community_name}",
                link_href=f"/community-admin/my-community/pending/{membership_id}",
            )
            logger.info(
                "community_join_request notification delivered recipient_user_id=%s notification_id=%s",
                admin_user_id,
                result.id if result else None,
            )
        except Exception:
            logger.exception(
                "Failed community_join_request notification recipient_user_id=%s community_id=%s",
                admin_user_id,
                community_id,
            )


def notify_job_application_approved(community_id: int, job_title: str, contract_id: int) -> None:
    notify_community_admins(
        community_id,
        notification_type="application_approved",
        title="Application approved",
        body=f'Your community was selected for “{job_title}”.',
        link_href=f"/community-admin/contracts/{contract_id}",
    )


def notify_job_application_rejected(community_id: int, job_title: str) -> None:
    notify_community_admins(
        community_id,
        notification_type="application_rejected",
        title="Application not selected",
        body=f'Your application to “{job_title}” was not selected this time.',
        link_href="/community-admin/jobs",
    )


def notify_membership_decision(user_id: int, community_name: str, approved: bool) -> None:
    deliver_notification(
        user_id,
        notification_type="member_approved" if approved else "member_rejected",
        title="Join request approved" if approved else "Join request declined",
        body=(
            f'You were approved to join “{community_name}”.'
            if approved
            else f'Your request to join “{community_name}” was declined.'
        ),
        link_href="/member/communities",
    )


def notify_contract_assigned(member_id: int, job_title: str, contract_id: int) -> None:
    deliver_notification(
        member_id,
        notification_type="contract_assigned",
        title="Contract assigned",
        body=f'You were assigned to “{job_title}”.',
        link_href=f"/member/contracts/{contract_id}",
    )


def notify_contract_application_rejected(member_id: int, job_title: str, contract_id: int) -> None:
    deliver_notification(
        member_id,
        notification_type="contract_application_rejected",
        title="Contract application not selected",
        body=f'You were not selected for “{job_title}”.',
        link_href=f"/community-admin/contracts/{contract_id}/applicants",
    )


def notify_contract_open_internally(community_id: int, job_title: str, contract_id: int) -> None:
    member_ids = [
        m.user_id
        for m in CommunityMember.query.filter_by(
            community_id=community_id, status="approved", role="member"
        ).all()
    ]
    deliver_to_users(
        member_ids,
        notification_type="contract_open_internally",
        title="New internal contract",
        body=f'“{job_title}” is open for member applications.',
        link_href=f"/member/contracts/{contract_id}",
    )


def notify_deliverable_submitted(community_id: int, job_title: str, contract_id: int) -> None:
    notify_community_admins(
        community_id,
        notification_type="deliverable_submitted",
        title="Deliverable submitted",
        body=f'A deliverable was submitted for “{job_title}”.',
        link_href=f"/community-admin/contracts/{contract_id}/review",
    )


def notify_deliverable_forwarded(poster_user_id: int, job_title: str, contract_id: int) -> None:
    deliver_notification(
        poster_user_id,
        notification_type="deliverable_forwarded",
        title="Deliverable ready for review",
        body=f'Community admin forwarded the deliverable for “{job_title}”.',
        link_href=f"/contracts/{contract_id}",
    )


def notify_deliverable_approved(member_id: int, job_title: str, contract_id: int) -> None:
    deliver_notification(
        member_id,
        notification_type="deliverable_approved",
        title="Deliverable approved",
        body=f'Your deliverable for "{job_title}" was approved and payment was released.',
        link_href=f"/member/contracts/{contract_id}",
    )


def notify_community_verification(community_id: int, community_name: str, verified: bool, reason: str | None = None) -> None:
    if verified:
        body = f"{community_name} was approved and is now visible on HireHub."
    else:
        body = f"{community_name} was not approved."
        if reason:
            body = f"{body} Reason: {reason}"
    notify_community_admins(
        community_id,
        notification_type="community_verified" if verified else "community_rejected",
        title="Community approved" if verified else "Community not approved",
        body=body,
        link_href="/community-admin/my-community",
    )


def notify_new_message(
    contract_id: int,
    community_id: int,
    job_id: int,
    sender_id: int,
    sender_name: str,
    preview: str,
) -> None:
    job = Job.query.get(job_id)
    recipient_ids: set[int] = set(get_community_admin_user_ids(community_id))
    if job and job.posted_by_id:
        recipient_ids.add(job.posted_by_id)
    recipient_ids.discard(sender_id)

    snippet = preview if len(preview) <= 120 else f"{preview[:117]}..."
    deliver_to_users(
        recipient_ids,
        notification_type="new_message",
        title=f"New message from {sender_name}",
        body=snippet,
        link_href=f"/contracts/{contract_id}/messages",
    )
