"""
Generate illustrative FAKE monthly enquiry-count history for the DEV
database, for module 20 (Time Series Demand Forecaster).

WHY A SEPARATE, LIGHTWEIGHT SCRIPT (not more seed_dev_fake_leads.py rows):
John chose the lightweight option when asked - this script writes only
aggregate (year, month, enquiry_count) rows to enquiry_monthly_history, not
full fake lead records. That also means it is completely independent of
seed_dev_fake_leads.py: enquiry_monthly_history has no foreign key to
leads/applicants/anything else, so this script can never be affected by, or
cascade-affect, any other seed script's data. It can be re-run in isolation.

WHAT GETS GENERATED: 3 synthetic years (2023, 2024, 2025), one row per
(year, month) = 36 rows. Each month's count is shaped by the SAME seasonal
weights (MONTH_W) that seed_dev_fake_leads.py already uses for real lead
enquiry_datetime - May/June admission season peak, Nov/Dec/Jan trough - so
the synthetic history has the same seasonal shape a real forecasting model
would need to learn. ANNUAL_TOTALS then applies a modest ~15%/year growth
trend on top, calibrated to lead naturally into the ~500/year real lead
volume already in DEV (from seed_dev_fake_leads.py) - so a 2026 line drawn
through this synthetic history and the real current year looks like one
continuous, plausible growth curve, not a discontinuity.

2026 ONWARD IS DELIBERATELY NOT SEEDED HERE. The module 20 training script
pulls 2026's real monthly counts directly from the leads table (grouped by
month of created_at) and appends them to this synthetic history - source
distinguishes the two: 'synthetic' for rows this script writes (also the
DB's own default), vs whatever the training/live-aggregation code uses for
real counts it computes on the fly (it does not need to write rows here at
all - it reads leads directly).

Safety rules (same shape as every other seed_dev_*.py script):
  * DEV ONLY. Uses DEV_SUPABASE_URL/KEY and refuses to run if they are empty
    or equal to the PROD credentials.
  * DRY-RUN BY DEFAULT. Nothing touches the database unless --apply is given.
    Note this script needs NO database access at all to generate or validate
    its rows (unlike seed_dev_fee_due_schedule.py, it reads nothing from
    DEV first) - only --apply/--delete touch the network.
  * --delete removes only rows with source='synthetic' - nothing else. Since
    this table has no other writer yet, that is everything this script ever
    inserted, and nothing a customer's real usage would ever produce.
  * Requires migration 0020 (enquiry_monthly_history table) applied on DEV.

Usage (from the API repo root, in the conda env):
    python scripts/seed_dev_enquiry_monthly_history.py                  # dry-run, prints all 36 rows
    python scripts/seed_dev_enquiry_monthly_history.py --apply
    python scripts/seed_dev_enquiry_monthly_history.py --delete         # dry-run: counts what would go
    python scripts/seed_dev_enquiry_monthly_history.py --delete --apply # really delete the synthetic rows

NOTE ON REALISM: the growth trend and per-month noise are a plausible,
hand-set illustrative shape - NOT calibrated to any real enquiry data (DCE
has no real CRM usage history yet). Fine for building/testing the
forecasting pipeline; do not present model accuracy from this data as if it
reflected real historical demand.
"""
import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TABLE = "enquiry_monthly_history"

# Same seasonal shape as seed_dev_fake_leads.py's MONTH_W (May/June
# admission-season peak). Kept as an independent copy, not an import - this
# script must stay runnable even if that file's internals change, same
# reasoning as seed_dev_fee_due_schedule.py's independent OCCUPATION_* maps.
MONTH_W = {1: 3, 2: 5, 3: 7, 4: 9, 5: 18, 6: 20, 7: 14, 8: 8, 9: 5, 10: 4, 11: 3, 12: 3}
MONTH_TOTAL_WEIGHT = sum(MONTH_W.values())

# ~15%/year growth, landing just under the ~500-508 real leads already in
# DEV for the current rolling year - so 2023 -> 2024 -> 2025 -> (real 2026)
# reads as one continuous, plausible growth curve rather than a jump.
ANNUAL_TOTALS = {2023: 340, 2024: 390, 2025: 450}
NOISE_RANGE = (0.85, 1.15)  # multiplicative, per month


def generate(seed: int) -> list[dict]:
    rng = random.Random(seed)
    rows = []
    for year in sorted(ANNUAL_TOTALS):
        annual_total = ANNUAL_TOTALS[year]
        for month in range(1, 13):
            base = annual_total * MONTH_W[month] / MONTH_TOTAL_WEIGHT
            noisy = base * rng.uniform(*NOISE_RANGE)
            count = max(1, round(noisy))
            rows.append({"year": year, "month": month, "enquiry_count": count})
    return rows


def validate_with_api_models(rows):
    from app.models.enquiry_monthly_history import EnquiryMonthlyHistoryCreate
    for row in rows:
        EnquiryMonthlyHistoryCreate(**row)


def print_report(rows):
    by_year = {}
    for r in rows:
        by_year.setdefault(r["year"], []).append(r)
    print(f"\nGenerated {len(rows)} enquiry_monthly_history rows across {len(by_year)} years:")
    for year in sorted(by_year):
        yr_rows = sorted(by_year[year], key=lambda r: r["month"])
        total = sum(r["enquiry_count"] for r in yr_rows)
        counts = ", ".join(f"{r['month']:02d}:{r['enquiry_count']}" for r in yr_rows)
        target = ANNUAL_TOTALS[year]
        print(f"  {year}  target={target:4d}  actual={total:4d}   {counts}")


def get_dev_client():
    from app.core.config import settings
    from supabase import create_client
    if not settings.DEV_SUPABASE_URL or not settings.DEV_SUPABASE_KEY:
        sys.exit("REFUSING: DEV_SUPABASE_URL / DEV_SUPABASE_KEY are not set.")
    if settings.DEV_SUPABASE_URL == settings.PROD_SUPABASE_URL or settings.DEV_SUPABASE_KEY == settings.PROD_SUPABASE_KEY:
        sys.exit("REFUSING: DEV credentials equal PROD credentials.")
    host = settings.DEV_SUPABASE_URL.split("//")[-1].split(".")[0]
    print(f"Target: DEV project ref {host}")
    return create_client(settings.DEV_SUPABASE_URL, settings.DEV_SUPABASE_KEY)


def chunks(rows, n=100):
    for i in range(0, len(rows), n):
        yield rows[i:i + n]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=42, help="same seed -> same data")
    ap.add_argument("--apply", action="store_true", help="really write (or delete); default is dry-run")
    ap.add_argument("--delete", action="store_true", help="remove the synthetic rows (source='synthetic')")
    ap.add_argument("--force", action="store_true", help="seed even if synthetic rows already exist")
    args = ap.parse_args()

    if args.delete:
        client = get_dev_client()
        existing = client.table(TABLE).select("id", count="exact").eq("source", "synthetic").limit(1).execute().count or 0
        print(f"Synthetic enquiry_monthly_history rows in DEV: {existing}")
        if not args.apply:
            print("Dry-run: nothing deleted. Add --apply to delete the synthetic rows.")
            return
        result = client.table(TABLE).delete().eq("source", "synthetic").execute()
        print(f"Deleted {len(result.data or [])} synthetic enquiry_monthly_history rows")
        return

    rows = generate(args.seed)
    validate_with_api_models(rows)
    print("All generated rows pass the API's own response models (no 500 risk).")
    print_report(rows)
    if not args.apply:
        print("\nDRY-RUN: nothing written. Re-run with --apply to write to DEV.")
        return

    client = get_dev_client()
    existing = client.table(TABLE).select("id", count="exact").eq("source", "synthetic").limit(1).execute().count or 0
    if existing and not args.force:
        sys.exit(f"REFUSING: {existing} synthetic enquiry_monthly_history rows already exist in DEV. Use --delete --apply first, or --force.")

    for part in chunks(rows):
        client.table(TABLE).insert(part).execute()
    print(f"Inserted enquiry_monthly_history: {len(rows)}")


if __name__ == "__main__":
    main()
