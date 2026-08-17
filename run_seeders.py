"""Seed HireHub database from seeders/data JSON files.

WARNING: This script DROPs all tables and reloads demo data. Run only when you
explicitly want a fresh database — not on every dev server start.
"""

import sys

from app import create_app
from app.extensions import db
from seeders.loader import run_seed


def seed(*, reset: bool = False):
    if not reset:
        print(
            "Refusing to seed: this script drops all tables and wipes your data.\n"
            "To load demo data anyway, run:\n"
            "  python run_seeders.py --reset"
        )
        sys.exit(1)

    app = create_app()
    with app.app_context():
        db.drop_all()
        db.create_all()
        run_seed(db.session)
        db.session.commit()
        print("Seed complete — example data loaded from seeders/data/.")
        print()
        print("Platform admin:  admin@gmail.com / admin123")
        print("User / job poster:       hassan@gmail.com / password1")
        print("Employer / community admin: perera@gmail.com / password2 (PixelForge Web Dev)")
        print("Employer / member:      sam.perera@example.com / Password123")


if __name__ == "__main__":
    reset = "--reset" in sys.argv or "-y" in sys.argv
    seed(reset=reset)
