"""Clean placeholder jobs and upsert realistic Sri Lankan example jobs.

Dry-run (default):
    python -m app.scripts.seed_realistic_jobs

Apply to the configured local database:
    python -m app.scripts.seed_realistic_jobs --apply
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import date, timedelta
from decimal import Decimal

from app import create_app
from app.extensions import db
from app.models.ai_match_blurb_model import AiMatchBlurb
from app.models.category_model import Category
from app.models.community_application_model import CommunityApplication
from app.models.contract_application_model import ContractApplication
from app.models.contract_model import Contract
from app.models.conversation_model import Conversation
from app.models.job_model import Job
from app.models.payment_model import Payment
from app.models.report_model import Report
from app.models.review_model import Review
from app.models.user_model import User


PLACEHOLDER_TITLE = re.compile(
    r"^\s*(?:\[(?:scope seed|scope test|seed|test)\]|test\b|asdf\b)", re.IGNORECASE
)

REALISTIC_JOBS = (
    {
        "title": "Company Website Redesign",
        "category": "Web Development",
        "description": (
            "Redesign our six-page Colombo business website with a modern responsive "
            "layout, CMS editing, contact-form integration, and basic SEO setup."
        ),
        "location": "Colombo",
        "days_until_deadline": 28,
        "price": "180000.00",
        "status": "open",
        "scope_data": {"pages": 6, "features": ["Blog/CMS"]},
    },
    {
        "title": "Blog Content for Travel Startup",
        "category": "Content Writing",
        "description": (
            "Write one researched 900-word article introducing authentic Kandy travel "
            "experiences, with an engaging title and search-friendly headings."
        ),
        "location": "Kandy",
        "days_until_deadline": 14,
        "price": "4500.00",
        "status": "open",
        "scope_data": {"word_count": 900, "content_type": "Blog Post"},
    },
    {
        "title": "Exterior House Painting — 2 Story Home",
        "category": "Painting",
        "description": (
            "Prepare and paint approximately 1,800 sq ft of exterior wall on a two-storey "
            "Galle home, including crack filling, primer, and two weatherproof coats."
        ),
        "location": "Galle",
        "days_until_deadline": 35,
        "price": "180000.00",
        "status": "open",
        "scope_data": {"area_sqft": 1800, "coats": 2},
    },
    {
        "title": "Logo & Brand Kit for New Cafe",
        "category": "Graphic Design",
        "description": (
            "Create a distinctive cafe logo, colour palette, typography guide, menu header, "
            "and social profile assets with two revision rounds."
        ),
        "location": "Colombo",
        "days_until_deadline": 21,
        "price": "12000.00",
        "status": "open",
        "scope_data": {
            "deliverables": ["Logo", "Brand Guide", "Social Media Kit"],
            "revisions": 2,
        },
    },
    {
        "title": "Leaking Kitchen Tap Repair",
        "category": "Plumbing",
        "description": (
            "Repair a leaking kitchen mixer tap in Jaffna and replace the worn cartridge "
            "or seals as needed. Closed because a local plumber has been selected."
        ),
        "location": "Jaffna",
        "days_until_deadline": 7,
        "price": "3000.00",
        "status": "closed",
        "scope_data": {"fixtures_count": 1, "job_type": "Repair"},
    },
    {
        "title": "Product Photography for Handmade Crafts",
        "category": "Photography",
        "description": (
            "Photograph 20 handmade products in Matara for an online catalogue, including "
            "clean-background and lifestyle images with colour-corrected delivery."
        ),
        "location": "Matara",
        "days_until_deadline": 18,
        "price": "15000.00",
        "status": "open",
        "scope_data": {"hours": 6, "package": "Standard"},
    },
)


def _placeholder_jobs() -> list[Job]:
    return [job for job in Job.query.order_by(Job.id).all() if PLACEHOLDER_TITLE.search(job.title or "")]


def _audit(job: Job) -> dict:
    contracts = Contract.query.filter_by(job_id=job.id).all()
    applications = CommunityApplication.query.filter_by(job_id=job.id).all()
    return {
        "id": job.id,
        "title": job.title,
        "status": job.status,
        "contract_ids": [contract.id for contract in contracts],
        "contract_statuses": [contract.status for contract in contracts],
        "community_application_ids": [application.id for application in applications],
    }


def _delete_completed_seed_graph(job: Job) -> None:
    contracts = Contract.query.filter_by(job_id=job.id).all()
    contract_ids = [contract.id for contract in contracts]
    if CommunityApplication.query.filter_by(job_id=job.id).count():
        raise RuntimeError(f"Refusing to delete job {job.id}: community applications exist")
    if any(contract.status != "completed" for contract in contracts):
        raise RuntimeError(f"Refusing to delete job {job.id}: active contract exists")

    if contract_ids:
        ContractApplication.query.filter(ContractApplication.contract_id.in_(contract_ids)).delete(
            synchronize_session=False
        )
        Payment.query.filter(Payment.contract_id.in_(contract_ids)).delete(synchronize_session=False)
        Review.query.filter(Review.contract_id.in_(contract_ids)).delete(synchronize_session=False)
        Report.query.filter(Report.contract_id.in_(contract_ids)).update(
            {Report.contract_id: None}, synchronize_session=False
        )
        conversations = Conversation.query.filter(Conversation.contract_id.in_(contract_ids)).all()
        for conversation in conversations:
            # Messages are owned by the conversation relationship.
            for message in conversation.messages.all():
                db.session.delete(message)
            db.session.delete(conversation)
        Contract.query.filter(Contract.id.in_(contract_ids)).delete(synchronize_session=False)

    AiMatchBlurb.query.filter_by(job_id=job.id).delete(synchronize_session=False)
    db.session.delete(job)


def _upsert_realistic_jobs() -> tuple[int, int]:
    poster = User.query.filter_by(role="user").order_by(User.id.asc()).first()
    if not poster:
        raise RuntimeError("No user-role account exists to own realistic seed jobs")

    created = updated = 0
    today = date.today()
    for seed in REALISTIC_JOBS:
        category = Category.query.filter_by(name=seed["category"]).first()
        if not category:
            raise RuntimeError(f"Required category is missing: {seed['category']}")
        job = Job.query.filter_by(title=seed["title"]).first()
        if job is None:
            job = Job(title=seed["title"], posted_by_id=poster.id, category_id=category.id)
            db.session.add(job)
            created += 1
        else:
            updated += 1
        job.posted_by_id = poster.id
        job.category_id = category.id
        job.description = seed["description"]
        job.location = seed["location"]
        job.deadline = today + timedelta(days=seed["days_until_deadline"])
        job.suggested_price = Decimal(seed["price"])
        job.final_price = Decimal(seed["price"])
        job.status = seed["status"]
        job.set_scope_data(seed["scope_data"])
    return created, updated


def run(*, apply: bool) -> dict:
    candidates = _placeholder_jobs()
    audit = [_audit(job) for job in candidates]
    blocked = [
        row
        for row in audit
        if row["community_application_ids"]
        or any(status != "completed" for status in row["contract_statuses"])
    ]
    result = {"apply": apply, "placeholder_jobs": audit, "blocked": blocked}
    if not apply:
        return result
    if blocked:
        raise RuntimeError(f"Cleanup blocked by referenced jobs: {json.dumps(blocked)}")

    for job in candidates:
        _delete_completed_seed_graph(job)
    created, updated = _upsert_realistic_jobs()
    db.session.commit()
    result.update(
        {
            "deleted_placeholder_jobs": len(candidates),
            "realistic_jobs_created": created,
            "realistic_jobs_updated": updated,
        }
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="commit cleanup and realistic jobs")
    args = parser.parse_args()
    app = create_app()
    with app.app_context():
        try:
            print(json.dumps(run(apply=args.apply), indent=2, default=str))
        except Exception:
            db.session.rollback()
            raise


if __name__ == "__main__":
    main()
