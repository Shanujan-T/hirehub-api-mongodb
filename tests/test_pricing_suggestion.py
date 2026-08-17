import pytest
from app import create_app
from app.config import Config
from app.extensions import db
from app.models.pricing_reference_model import PricingReference
from app.utils.pricing_utils import suggest_price


@pytest.fixture(scope="module")
def test_app():
    # Flask-SQLAlchemy binds during create_app(); configure the test database first.
    Config.SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    Config.SQLALCHEMY_ENGINE_OPTIONS = {}
    app = create_app()
    app.config.update(
        {
            "TESTING": True,
        }
    )

    with app.app_context():
        db.create_all()

        # Seed test data
        references = [
            # Content Writing: Quantity-scaled (300, 500, 1000, 2500)
            PricingReference(
                category="Content Writing",
                scope="300 words",
                unit="words",
                quantity=300,
                base_price=1000,
            ),
            PricingReference(
                category="Content Writing",
                scope="500 words",
                unit="words",
                quantity=500,
                base_price=1500,
            ),
            PricingReference(
                category="Content Writing",
                scope="1000 words",
                unit="words",
                quantity=1000,
                base_price=3000,
            ),
            PricingReference(
                category="Content Writing",
                scope="2500 words",
                unit="words",
                quantity=2500,
                base_price=7500,
            ),
            # Plumbing: Flat (Leak repair 2500, Sink install 7000, Bathroom plumbing 40000)
            PricingReference(
                category="Plumbing",
                scope="Leak repair",
                unit="job",
                quantity=1,
                base_price=2500,
            ),
            PricingReference(
                category="Plumbing",
                scope="Sink install",
                unit="job",
                quantity=1,
                base_price=7000,
            ),
            PricingReference(
                category="Plumbing",
                scope="Bathroom plumbing",
                unit="job",
                quantity=1,
                base_price=40000,
            ),
        ]
        db.session.bulk_save_objects(references)
        db.session.commit()

        yield app

        db.session.remove()
        db.drop_all()


def test_exact_tier_match(test_app):
    with test_app.app_context():
        # Exact match 300 words: Colombo (1.30) -> 1000 * 1.30 = 1300
        assert suggest_price("Content Writing", 300, "Colombo") == 1300
        # Exact match 500 words: Gampaha (1.20) -> 1500 * 1.20 = 1800
        assert suggest_price("Content Writing", 500, "Gampaha") == 1800


def test_interpolation_between_tiers(test_app):
    with test_app.app_context():
        # Interpolate between 300 words (1000, rate 3.33) and 500 words (1500, rate 3.0)
        # For quantity 400:
        # t = (400 - 300) / (500 - 300) = 0.5
        # rate_300 = 1000/300 = 3.3333333333333335
        # rate_500 = 1500/500 = 3.0
        # interpolated rate = 3.3333333333333335 + 0.5 * (3.0 - 3.3333333333333335) = 3.1666666666666665
        # basePrice = 3.1666666666666665 * 400 = 1266.6666666666665
        # Colombo (1.30) -> 1266.6666666666665 * 1.30 = 1646.6666666666665
        # Nearest 50 LKR -> 1650
        assert suggest_price("Content Writing", 400, "Colombo") == 1650


def test_extrapolation_above_top_tier(test_app):
    with test_app.app_context():
        # Extrapolate above 2500 words (7500, rate 3.0)
        # For quantity 3000:
        # basePrice = 3.0 * 3000 = 9000
        # Colombo (1.30) -> 9000 * 1.30 = 11700
        # Nearest 50 LKR -> 11700
        assert suggest_price("Content Writing", 3000, "Colombo") == 11700


def test_below_lowest_tier(test_app):
    with test_app.app_context():
        # Below lowest tier 300 words: use lowest tier rate (1000/300 = 3.333)
        # For quantity 150:
        # basePrice = 3.3333333333333335 * 150 = 500
        # Colombo (1.30) -> 500 * 1.30 = 650
        # Nearest 50 LKR -> 650
        assert suggest_price("Content Writing", 150, "Colombo") == 650


def test_flat_category_lookup(test_app):
    with test_app.app_context():
        # Substring match "Repair" -> "Leak repair" (2500)
        # Colombo (1.30) -> 2500 * 1.30 = 3250
        assert suggest_price("Plumbing", 1, "Colombo", "Repair") == 3250

        # Substring match "install" -> "Sink install" (7000)
        # Kandy (1.15) -> 7000 * 1.15 = 8050 -> Nearest 50 -> 8050
        assert suggest_price("Plumbing", 1, "Kandy", "Installation") == 8050


def test_unknown_district_fallback(test_app):
    with test_app.app_context():
        # Unknown district -> multiplier 1.00
        # Content Writing 300 words: 1000 * 1.00 = 1000
        assert suggest_price("Content Writing", 300, "UnknownDistrict") == 1000


def test_unknown_category_fallback(test_app):
    with test_app.app_context():
        # Unknown category -> returns None
        assert suggest_price("Unknown Category", 100, "Colombo") is None
