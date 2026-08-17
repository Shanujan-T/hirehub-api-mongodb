"""
Run idempotent SQL migrations in order (local dev and Railway deploy).

Usage (from hirehub-api-02 root):
  set PYTHONPATH=.
  python migrations/run_all.py
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MIGRATION_MODULES = [
    "migrations.001_bidding_and_messaging",
    "migrations.002_community_image_url",
    "migrations.003_employer_to_client",
    "migrations.004_identity_and_community_verification",
    "migrations.005_user_role_and_posted_by",
    "migrations.006_identity_otp_phone_email",
    "migrations.007_user_address",
    "migrations.008_account_verify_phone_or_email",
    "migrations.009_notifications",
    "migrations.010_message_deletion",
    "migrations.011_ai_match_blurbs",
    "migrations.012_ai_review_digests",
    "migrations.013_open_call_description",
    "migrations.014_category_job_scope",
    "migrations.015_category_requests",
    "migrations.016_seed_example_scope_schemas",
    "migrations.017_bulk_scope_schemas",
    "migrations.018_category_baseline_price",
    "migrations.019_contract_health_risk",
    "migrations.020_work_samples",
    "migrations.021_community_application_source",
    "migrations.022_category_pricing_units",
    "migrations.023_district_pricing_seed",
    "migrations.024_scope_fields_affects_price",
    "migrations.025_contract_application_origin_and_payout",
    "migrations.026_category_baseline_scope_key",
    "migrations.027_pricing_reference",
    "migrations.028_pricing_reference_district_prices",
    "migrations.029_align_csv_pricing_scopes",
    "migrations.030_photography_event_time",
    "migrations.031_reintroduce_employer_role",
    "migrations.032_reporting_system",
]


def run_all() -> None:
    for module_name in MIGRATION_MODULES:
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError:
            print(f"Skip missing module: {module_name}")
            continue
        runner = getattr(module, "run_migration", None)
        if not callable(runner):
            print(f"Skip (no run_migration): {module_name}")
            continue
        print(f"--- {module_name} ---")
        runner()
    print("All migrations finished.")


if __name__ == "__main__":
    run_all()
