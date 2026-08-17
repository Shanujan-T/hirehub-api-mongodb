"""Align built-in category scope choices with the service-pricing CSV rows."""

from app import create_app
from app.extensions import db
from app.models.category_model import Category


CSV_SCHEMAS = {
    "Content Writing": [
        {"key": "word_count", "label": "Word count", "type": "number", "unit": "words", "required": True, "affects_price": True, "unit_size": 1},
        {"key": "content_type", "label": "Content type", "type": "select", "required": True, "options": ["Blog Post", "Website Copy", "Technical Docs"]},
    ],
    "Data Entry": [
        {"key": "record_count", "label": "Record count", "type": "number", "unit": "records", "required": True, "affects_price": True, "unit_size": 1},
    ],
    "Painting": [
        {"key": "paint_scope", "label": "Painting scope", "type": "select", "required": True, "options": ["One wall", "One room", "Whole house"]},
    ],
    "Plumbing": [
        {"key": "service_type", "label": "Service type", "type": "select", "required": True, "options": ["Leak repair", "Sink install", "Bathroom plumbing"]},
    ],
    "Electrical": [
        {"key": "service_type", "label": "Service type", "type": "select", "required": True, "options": ["Switch/socket", "Room wiring", "House wiring"]},
    ],
    "Web Development": [
        {"key": "site_tier", "label": "Website scope", "type": "select", "required": True, "options": ["Landing page", "Business website", "Ecommerce"]},
    ],
    "Graphic Design": [
        {"key": "design_scope", "label": "Design scope", "type": "select", "required": True, "options": ["Social post", "Brochure", "Brand package"]},
    ],
    "Mobile Repair": [
        {"key": "repair_type", "label": "Repair type", "type": "select", "required": True, "options": ["Screen replace", "Battery replace", "Motherboard"]},
    ],
}


def run_migration():
    app = create_app()
    with app.app_context():
        updated = 0
        for name, schema in CSV_SCHEMAS.items():
            category = Category.query.filter_by(name=name).first()
            if not category:
                continue
            category.set_scope_schema(schema)
            category.baseline_scope_key = "word_count" if name == "Content Writing" else ("record_count" if name == "Data Entry" else None)
            updated += 1
        db.session.commit()
        print(f"Migration complete: aligned CSV scopes for {updated} categories.")


if __name__ == "__main__":
    run_migration()
