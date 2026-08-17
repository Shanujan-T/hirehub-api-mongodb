"""Idempotent bulk seed: category scope_schema + historical completed jobs with scope_data.

Safe to re-run. Does not wipe the database.
Usage (from hirehub-api-02):
  set PYTHONPATH=.
  python -m seeders.seed_scope_schemas
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal

from app import create_app
from app.extensions import db
from app.models.category_model import Category
from app.models.contract_model import Contract
from app.models.job_model import Job
from app.models.user_model import User
from app.utils import utc_now

SCOPE_SCHEMAS: dict[str, list[dict]] = {
    "Web Development": [
        {"key": "pages", "label": "Number of pages", "type": "number", "affects_price": False, "unit_size": 1},
        {
            "key": "features",
            "label": "Features needed",
            "type": "multiselect",
            "options": [
                "Portfolio",
                "Blog/CMS",
                "E-commerce",
                "User Auth",
                "Payment Integration",
                "Custom Admin Dashboard",
            ],
        },
    ],
    "Landscaping": [
        {
            "key": "area_sqft",
            "label": "Area (sq ft)",
            "type": "number",
            "unit": "sq ft",
            "affects_price": True,
            "unit_size": 1,
        },
    ],
    "Plumbing": [
        {"key": "fixtures_count", "label": "Number of fixtures", "type": "number", "affects_price": False, "unit_size": 1},
        {
            "key": "job_type",
            "label": "Job type",
            "type": "select",
            "options": ["Repair", "Installation", "Emergency"],
        },
    ],
    "Electrical": [
        {"key": "rooms_count", "label": "Number of rooms", "type": "number", "affects_price": False, "unit_size": 1},
        {
            "key": "job_type",
            "label": "Job type",
            "type": "select",
            "options": ["Repair", "New Wiring", "Inspection"],
        },
    ],
    "Graphic Design": [
        {
            "key": "deliverables",
            "label": "Deliverables needed",
            "type": "multiselect",
            "options": [
                "Logo",
                "Brand Guide",
                "Business Cards",
                "Social Media Kit",
                "Packaging Design",
                "Print Ads",
            ],
        },
        {"key": "revisions", "label": "Number of revision rounds", "type": "number", "affects_price": False, "unit_size": 1},
    ],
    "Carpentry": [
        {
            "key": "area_sqft",
            "label": "Area (sq ft)",
            "type": "number",
            "unit": "sq ft",
            "affects_price": False,
            "unit_size": 1,
        },
        {
            "key": "material",
            "label": "Material",
            "type": "select",
            "options": ["Softwood", "Hardwood", "Composite"],
        },
    ],
    "Photography": [
        {
            "key": "hours",
            "label": "Estimated hours",
            "type": "number",
            "affects_price": True,
            "unit_size": 1,
        },
        {
            "key": "package",
            "label": "Package",
            "type": "select",
            "options": ["Basic", "Standard", "Premium"],
        },
    ],
    "Content Writing": [
        {
            "key": "word_count",
            "label": "Word count",
            "type": "number",
            "affects_price": True,
            "unit_size": 100,
            "required": True,
        },
        {
            "key": "content_type",
            "label": "Content type",
            "type": "select",
            "options": ["Blog Post", "Website Copy", "Technical Docs"],
            "affects_price": False,
        },
    ],
    "Painting": [
        {
            "key": "area_sqft",
            "label": "Area (sq ft)",
            "type": "number",
            "unit": "sq ft",
            "affects_price": True,
            "unit_size": 1,
        },
        {"key": "coats", "label": "Number of coats", "type": "number", "affects_price": False, "unit_size": 1},
    ],
    "HVAC": [
        {"key": "units_count", "label": "Number of units", "type": "number", "affects_price": False, "unit_size": 1},
        {
            "key": "job_type",
            "label": "Job type",
            "type": "select",
            "options": ["Repair", "Installation", "Maintenance"],
        },
    ],
    "Roofing": [
        {
            "key": "area_sqft",
            "label": "Area (sq ft)",
            "type": "number",
            "unit": "sq ft",
            "affects_price": False,
            "unit_size": 1,
        },
        {
            "key": "job_type",
            "label": "Job type",
            "type": "select",
            "options": ["Repair", "Replacement", "Inspection"],
        },
    ],
    "Tiling": [
        {
            "key": "area_sqft",
            "label": "Area (sq ft)",
            "type": "number",
            "unit": "sq ft",
            "affects_price": False,
            "unit_size": 1,
        },
        {
            "key": "surface",
            "label": "Surface",
            "type": "select",
            "options": ["Floor", "Wall", "Bathroom", "Kitchen Backsplash"],
        },
    ],
    "Welding": [
        {
            "key": "hours",
            "label": "Estimated hours",
            "type": "number",
            "affects_price": True,
            "unit_size": 1,
        },
        {
            "key": "job_type",
            "label": "Job type",
            "type": "select",
            "options": ["Repair", "Fabrication", "On-site Welding"],
        },
    ],
    "Home Cleaning": [
        {"key": "rooms_count", "label": "Number of rooms", "type": "number", "affects_price": False, "unit_size": 1},
        {
            "key": "cleaning_type",
            "label": "Cleaning type",
            "type": "select",
            "options": ["Standard", "Deep Clean", "Move-out"],
        },
    ],
    "Moving Services": [
        {"key": "rooms_count", "label": "Number of rooms", "type": "number", "affects_price": False, "unit_size": 1},
        {
            "key": "distance",
            "label": "Distance",
            "type": "select",
            "options": ["Local", "Intercity", "Long Distance"],
        },
    ],
    "IT Support": [
        {"key": "devices_count", "label": "Number of devices", "type": "number", "affects_price": False, "unit_size": 1},
        {
            "key": "support_type",
            "label": "Support type",
            "type": "select",
            "options": ["Setup", "Troubleshooting", "Network", "Security"],
        },
    ],
    "Data Entry": [
        {"key": "record_count", "label": "Number of records", "type": "number", "affects_price": False, "unit_size": 1},
        {
            "key": "format",
            "label": "Source format",
            "type": "select",
            "options": ["Spreadsheets", "Scanned Docs", "Forms", "Database Export"],
        },
    ],
    "Video Editing": [
        {"key": "minutes", "label": "Video length (minutes)", "type": "number", "affects_price": False, "unit_size": 1},
        {
            "key": "edit_type",
            "label": "Edit type",
            "type": "select",
            "options": ["Basic Cut", "Color Grade", "Motion Graphics", "Full Production"],
        },
    ],
    "Social Media Marketing": [
        {"key": "posts_per_month", "label": "Posts per month", "type": "number", "affects_price": False, "unit_size": 1},
        {
            "key": "platforms",
            "label": "Platforms",
            "type": "multiselect",
            "options": ["Instagram", "Facebook", "TikTok", "LinkedIn", "YouTube"],
        },
    ],
    "Mobile App Development": [
        {"key": "screens", "label": "Number of screens", "type": "number", "affects_price": False, "unit_size": 1},
        {
            "key": "platforms",
            "label": "Platforms",
            "type": "multiselect",
            "options": ["iOS", "Android", "Cross-platform"],
        },
    ],
}

# Primary pricing locations from category_pricing seed (category name → location)
_PRIMARY_LOCATION = {
    "Web Development": "Colombo",
    "Plumbing": "Kandy",
    "Electrical": "Galle",
    "Carpentry": "Kandy",
    "Photography": "Matara",
    "Painting": "Negombo",
    "Content Writing": "Colombo",
    "Landscaping": "Kandy",
}

TITLE_PREFIX = "[Scope seed]"

# LKR baseline estimates used when no local historical pricing exists.
BASELINE_PRICES: dict[str, tuple[float, str | None]] = {
    "Painting": (100, "area_sqft"),
    "Landscaping": (150, "area_sqft"),
    "Plumbing": (6000, None),
    "Electrical": (7000, None),
    "Carpentry": (40, "area_sqft"),
    "Web Development": (75000, None),
    "Graphic Design": (10000, None),
    "Photography": (1500, "hours"),
    "Content Writing": (25, "word_count"),
    "Home Cleaning": (5000, None),  # seed list "Cleaning"
}


def apply_baseline_prices() -> int:
    updated = 0
    for name, (price, scope_key) in BASELINE_PRICES.items():
        cat = Category.query.filter_by(name=name).first()
        if not cat:
            # Alias support
            if name == "Home Cleaning":
                cat = Category.query.filter_by(name="Cleaning").first()
            if not cat:
                print(f"Skip baseline: category '{name}' not found")
                continue
        cat.baseline_price = price
        cat.baseline_scope_key = scope_key
        updated += 1
        print(f"Set baseline: {cat.name} = {price} ({scope_key})")
    return updated


def _historical_rows() -> list[dict]:
    """At least 3 completed jobs per scoped category, same location, realistic scope_data."""
    rows: list[dict] = []

    # Web Development — Colombo (pages × ~250 + feature premiums)
    for i, (pages, features, amount) in enumerate(
        [
            (5, ["Portfolio", "Blog/CMS"], 1800),
            (10, ["Portfolio", "User Auth", "Custom Admin Dashboard"], 3200),
            (8, ["E-commerce", "User Auth", "Payment Integration"], 4100),
            (12, ["Blog/CMS", "E-commerce", "Payment Integration"], 4500),
        ],
        start=1,
    ):
        rows.append(
            {
                "category": "Web Development",
                "title": f"{TITLE_PREFIX} Web site #{i}",
                "location": "Colombo",
                "amount": amount,
                "scope_data": {"pages": pages, "features": features},
            }
        )

    # Landscaping — Kandy (area 200–2000, ~0.35–0.55 / sqft)
    for i, (area, amount) in enumerate(
        [(280, 120), (650, 280), (1200, 520), (1800, 780)], start=1
    ):
        rows.append(
            {
                "category": "Landscaping",
                "title": f"{TITLE_PREFIX} Landscape job #{i}",
                "location": "Kandy",
                "amount": amount,
                "scope_data": {"area_sqft": area},
            }
        )

    # Plumbing — Kandy
    for i, (fixtures, job_type, amount) in enumerate(
        [
            (2, "Repair", 95),
            (5, "Installation", 240),
            (3, "Emergency", 180),
            (8, "Installation", 360),
        ],
        start=1,
    ):
        rows.append(
            {
                "category": "Plumbing",
                "title": f"{TITLE_PREFIX} Plumbing job #{i}",
                "location": "Kandy",
                "amount": amount,
                "scope_data": {"fixtures_count": fixtures, "job_type": job_type},
            }
        )

    # Electrical — Galle
    for i, (rooms, job_type, amount) in enumerate(
        [
            (2, "Repair", 140),
            (4, "New Wiring", 380),
            (3, "Inspection", 160),
            (6, "New Wiring", 520),
        ],
        start=1,
    ):
        rows.append(
            {
                "category": "Electrical",
                "title": f"{TITLE_PREFIX} Electrical job #{i}",
                "location": "Galle",
                "amount": amount,
                "scope_data": {"rooms_count": rooms, "job_type": job_type},
            }
        )

    # Carpentry — Kandy
    for i, (area, material, amount) in enumerate(
        [
            (120, "Softwood", 320),
            (250, "Hardwood", 680),
            (180, "Composite", 450),
            (400, "Hardwood", 980),
        ],
        start=1,
    ):
        rows.append(
            {
                "category": "Carpentry",
                "title": f"{TITLE_PREFIX} Carpentry job #{i}",
                "location": "Kandy",
                "amount": amount,
                "scope_data": {"area_sqft": area, "material": material},
            }
        )

    # Photography — Matara
    for i, (hours, package, amount) in enumerate(
        [
            (3, "Basic", 180),
            (6, "Standard", 360),
            (8, "Premium", 520),
            (4, "Standard", 280),
        ],
        start=1,
    ):
        rows.append(
            {
                "category": "Photography",
                "title": f"{TITLE_PREFIX} Photography job #{i}",
                "location": "Matara",
                "amount": amount,
                "scope_data": {"hours": hours, "package": package},
            }
        )

    # Content Writing — Colombo
    for i, (words, content_type, amount) in enumerate(
        [
            (800, "Blog Post", 90),
            (1500, "Website Copy", 180),
            (3000, "Technical Docs", 320),
            (1200, "Blog Post", 130),
        ],
        start=1,
    ):
        rows.append(
            {
                "category": "Content Writing",
                "title": f"{TITLE_PREFIX} Writing job #{i}",
                "location": "Colombo",
                "amount": amount,
                "scope_data": {"word_count": words, "content_type": content_type},
            }
        )

    # Painting — Negombo
    for i, (area, coats, amount) in enumerate(
        [
            (400, 1, 160),
            (900, 2, 340),
            (1500, 2, 520),
            (600, 3, 280),
        ],
        start=1,
    ):
        rows.append(
            {
                "category": "Painting",
                "title": f"{TITLE_PREFIX} Painting job #{i}",
                "location": "Negombo",
                "amount": amount,
                "scope_data": {"area_sqft": area, "coats": coats},
            }
        )

    # Graphic Design — Colombo
    for i, (deliverables, revisions, amount) in enumerate(
        [
            (["Logo"], 2, 280),
            (["Logo", "Brand Guide", "Business Cards"], 3, 650),
            (["Social Media Kit", "Print Ads"], 2, 420),
            (["Logo", "Packaging Design"], 4, 780),
        ],
        start=1,
    ):
        rows.append(
            {
                "category": "Graphic Design",
                "title": f"{TITLE_PREFIX} Design job #{i}",
                "location": "Colombo",
                "amount": amount,
                "scope_data": {"deliverables": deliverables, "revisions": revisions},
            }
        )

    return rows


def apply_scope_schemas() -> int:
    updated = 0
    for name, schema in SCOPE_SCHEMAS.items():
        cat = Category.query.filter_by(name=name).first()
        if not cat:
            print(f"Skip schema: category '{name}' not found")
            continue
        cat.set_scope_schema(schema)
        if cat.status != "approved":
            cat.status = "approved"
        updated += 1
        print(f"Set scope_schema: {name}")

    missing = [
        c.name
        for c in Category.query.order_by(Category.name.asc()).all()
        if not c.get_scope_schema()
    ]
    if missing:
        print(f"Still without scope_schema (intentional or unknown): {missing}")
    else:
        print("All categories now have a scope_schema.")
    return updated


def _poster_id() -> int:
    user = User.query.filter_by(role="user").order_by(User.id.asc()).first()
    if user:
        return user.id
    admin = User.query.order_by(User.id.asc()).first()
    if not admin:
        raise RuntimeError("No users found — run full seeders first.")
    return admin.id


def _community_id_for_category(category_id: int) -> int | None:
    from app.models.community_model import Community

    community = (
        Community.query.filter_by(category_id=category_id, status="approved")
        .order_by(Community.id.asc())
        .first()
    )
    if community:
        return community.id
    any_approved = Community.query.filter_by(status="approved").order_by(Community.id.asc()).first()
    return any_approved.id if any_approved else None


def _member_for_community(community_id: int) -> int | None:
    from app.models.community_member_model import CommunityMember

    member = (
        CommunityMember.query.filter_by(community_id=community_id, status="approved")
        .order_by(CommunityMember.id.asc())
        .first()
    )
    return member.user_id if member else None


def apply_historical_jobs() -> int:
    """Retained for compatibility; placeholder historical jobs are deprecated."""
    print("Skip: legacy [Scope seed] historical job generation is disabled.")
    return 0


def run() -> None:
    app = create_app()
    with app.app_context():
        schemas = apply_scope_schemas()
        baselines = apply_baseline_prices()
        jobs = apply_historical_jobs()
        db.session.commit()
        print(
            json.dumps(
                {
                    "schemas_updated": schemas,
                    "baselines_updated": baselines,
                    "jobs_created_or_refreshed": jobs,
                },
                indent=2,
            )
        )

        # Quick verify
        for name in ("Landscaping", "Web Development", "Home Cleaning"):
            cat = Category.query.filter_by(name=name).first()
            schema = cat.get_scope_schema() if cat else None
            print(
                f"verify {name}: fields={[f.get('key') for f in (schema or [])]} "
                f"baseline={getattr(cat, 'baseline_price', None)} "
                f"scope_key={getattr(cat, 'baseline_scope_key', None)}"
            )


if __name__ == "__main__":
    run()
