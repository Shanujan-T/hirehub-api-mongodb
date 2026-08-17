"""Load example datasets from seeders/data into the database."""

import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import List

from app.models.category_model import Category
from app.models.category_pricing_model import CategoryPricing
from app.models.community_application_model import CommunityApplication
from app.models.community_member_model import CommunityMember
from app.models.community_model import Community
from app.models.contract_application_model import ContractApplication
from app.models.contract_model import Contract
from app.models.job_model import Job
from app.models.open_call_model import OpenCall
from app.models.open_call_skill_model import OpenCallSkill
from app.models.payment_model import Payment
from app.models.report_model import Report
from app.models.review_model import Review
from app.models.skill_model import Skill
from app.models.user_model import User
from app.models.user_skill_model import UserSkill
from app.utils import utc_now

DATA_DIR = Path(__file__).parent / "data"

LOAD_ORDER = [
    "users",
    "skills",
    "categories",
    "category_pricing",
    "communities",
    "community_members",
    "user_skills",
    "jobs",
    "community_applications",
    "contracts",
    "contract_applications",
    "open_calls",
    "open_call_skills",
    "reviews",
    "payments",
    "reports",
]


def _load_json(name: str) -> List[dict]:
    path = DATA_DIR / f"{name}.json"
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _parse_datetime(value: str | None):
    if not value:
        return None
    if "T" in value:
        return datetime.fromisoformat(value)
    return datetime.combine(_parse_date(value), datetime.min.time())


def run_seed(session) -> None:
    """Insert all seeder files in FK-safe order. User id 21 is the platform admin."""
    now = utc_now()

    for row in _load_json("users"):
        user = User(
            email=row["email"],
            full_name=row["full_name"],
            role=row["role"],
            location=row.get("location"),
            bio=row.get("bio"),
            is_active=row.get("is_active", True),
            created_at=_parse_datetime(row.get("created_at")) or now,
        )
        user.set_password(row.get("password", "Password123"))
        session.add(user)

    session.flush()

    for row in _load_json("skills"):
        session.add(
            Skill(
                name=row["name"],
                category=row.get("category"),
            )
        )

    session.flush()

    for row in _load_json("categories"):
        cat = Category(
            name=row["name"],
            status=row.get("status", "approved"),
            requested_by_id=row.get("requested_by_id"),
            request_description=row.get("request_description") or row.get("description"),
            rejection_reason=row.get("rejection_reason"),
        )
        if row.get("scope_schema") is not None:
            cat.set_scope_schema(row["scope_schema"])
        if row.get("baseline_price") is not None:
            cat.baseline_price = row["baseline_price"]
        if "baseline_scope_key" in row:
            cat.baseline_scope_key = row["baseline_scope_key"]
        session.add(cat)

    session.flush()

    for row in _load_json("category_pricing"):
        session.add(
            CategoryPricing(
                category_id=row["category_id"],
                location=row["location"],
                average_price=Decimal(str(row["average_price"])),
                sample_size=row["sample_size"],
                last_updated=_parse_datetime(row.get("last_updated")) or now,
            )
        )

    session.flush()

    for row in _load_json("communities"):
        session.add(
            Community(
                name=row["name"],
                description=row.get("description"),
                location=row.get("location"),
                category_id=row.get("category_id", 1),
                experience_level=row.get("experience_level", "1_to_3_years"),
                specialization=row.get("specialization"),
                portfolio_links=row.get("portfolio_links"),
                admin_bio=row.get("admin_bio"),
                contact_phone=row.get("contact_phone"),
                status=row.get("status", "approved"),
                reputation_score=row.get("reputation_score", 0.0),
            )
        )

    session.flush()

    community_member_rows = _load_json("community_members")
    for row in community_member_rows:
        session.add(
            CommunityMember(
                community_id=row["community_id"],
                user_id=row["user_id"],
                role=row["role"],
                status=row["status"],
                joined_at=_parse_datetime(row.get("joined_at")) or now,
            )
        )

    # Seed memberships identify the accounts that do community work.
    community_user_ids = {row["user_id"] for row in community_member_rows}
    for community_user_id in community_user_ids:
        seeded_user = session.get(User, community_user_id)
        if seeded_user and seeded_user.role != "admin":
            seeded_user.role = "employer"

    session.flush()

    for row in _load_json("user_skills"):
        session.add(
            UserSkill(
                user_id=row["user_id"],
                skill_id=row["skill_id"],
                level=row["level"],
            )
        )

    session.flush()

    for row in _load_json("jobs"):
        job = Job(
            posted_by_id=row["posted_by_id"],
            category_id=row["category_id"],
            title=row["title"],
            description=row["description"],
            location=row["location"],
            deadline=_parse_date(row["deadline"]),
            suggested_price=Decimal(str(row["suggested_price"])) if row.get("suggested_price") is not None else None,
            final_price=Decimal(str(row["final_price"])),
            status=row["status"],
        )
        if row.get("scope_data") is not None:
            job.set_scope_data(row["scope_data"])
        session.add(job)

    session.flush()

    for row in _load_json("community_applications"):
        session.add(
            CommunityApplication(
                job_id=row["job_id"],
                community_id=row["community_id"],
                status=row["status"],
                proposed_cost=Decimal(str(row.get("proposed_cost", 100))),
                proposed_days=int(row.get("proposed_days", 7)),
                note=row.get("note"),
                applied_at=_parse_datetime(row.get("applied_at")) or now,
            )
        )

    session.flush()

    for row in _load_json("contracts"):
        session.add(
            Contract(
                job_id=row["job_id"],
                community_id=row["community_id"],
                assigned_member_id=row.get("assigned_member_id"),
                total_amount=Decimal(str(row["total_amount"])),
                commission_percent=Decimal(str(row.get("commission_percent", 3))),
                commission_amount=Decimal(str(row["commission_amount"])) if row.get("commission_amount") is not None else None,
                member_payout=Decimal(str(row["member_payout"])) if row.get("member_payout") is not None else None,
                status=row["status"],
                deliverable_url=row.get("deliverable_url"),
            )
        )

    session.flush()

    for row in _load_json("contract_applications"):
        session.add(
            ContractApplication(
                contract_id=row["contract_id"],
                member_id=row["member_id"],
                note=row.get("note"),
                status=row["status"],
                applied_at=_parse_datetime(row.get("applied_at")) or now,
            )
        )

    session.flush()

    for row in _load_json("open_calls"):
        session.add(
            OpenCall(
                community_id=row["community_id"],
                title=row["title"],
                status=row["status"],
            )
        )

    session.flush()

    for row in _load_json("open_call_skills"):
        session.add(
            OpenCallSkill(
                open_call_id=row["open_call_id"],
                skill_id=row["skill_id"],
            )
        )

    session.flush()

    for row in _load_json("reviews"):
        session.add(
            Review(
                contract_id=row["contract_id"],
                reviewer_id=row["reviewer_id"],
                community_id=row["community_id"],
                member_id=row.get("member_id"),
                rating=row["rating"],
                comment=row.get("comment"),
            )
        )

    session.flush()

    for row in _load_json("payments"):
        session.add(
            Payment(
                contract_id=row["contract_id"],
                total_amount=Decimal(str(row["total_amount"])),
                commission_amount=Decimal(str(row["commission_amount"])),
                commission_recipient=row.get("commission_recipient", "admin"),
                member_payout=Decimal(str(row["member_payout"])),
                status=row["status"],
                released_at=_parse_datetime(row.get("released_at")),
            )
        )

    session.flush()

    for row in _load_json("reports"):
        session.add(
            Report(
                reporter_id=row["reporter_id"],
                reporter_role="user",
                target_type="user",
                target_id=row["reporter_id"],
                reason="other",
                description=row["reason"],
                status=row["status"],
            )
        )

    session.flush()

    _refresh_community_reputation(session)

    # Ensure scope schemas and baseline prices are available for pricing demos.
    # Realistic example jobs are loaded separately; do not recreate the legacy
    # ``[Scope seed]`` historical jobs that leaked into user-facing job lists.
    from seeders.seed_scope_schemas import (
        apply_baseline_prices,
        apply_scope_schemas,
    )

    apply_scope_schemas()
    apply_baseline_prices()
    session.flush()

    from app.utils.pricing_utils import seed_district_pricing

    seed_district_pricing()
    session.flush()


def _refresh_community_reputation(session) -> None:
    from sqlalchemy import func

    averages = (
        session.query(Review.community_id, func.avg(Review.rating))
        .group_by(Review.community_id)
        .all()
    )
    for community_id, avg_rating in averages:
        community = session.get(Community, community_id)
        if community and avg_rating is not None:
            community.reputation_score = round(float(avg_rating), 2)
