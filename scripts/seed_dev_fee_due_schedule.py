"""
Generate realistic FAKE fee-due-schedule + fee-payment history for the DEV
database, for module 18 (Fee Default Risk Predictor).

Why a SEPARATE script from seed_dev_fake_leads.py: that script's generate()
uses one shared random.Random() stream where any change to the number/type
of rng calls shifts every downstream draw - adding fee logic there would
force a full leads/applicants/applications/followups/call_schedules
regenerate for an unrelated change. This script instead READS the already-
seeded Admitted applicants/applications (marker email, see that script) and
only adds new rows to fee_due_schedule/fee_payments - it cannot perturb
anything that script already wrote.

WHO GETS A FEE SCHEDULE: only applications with application_stage='Admitted'
- these are the applicants who actually enrolled and therefore have a real
fee obligation. Everyone else (Draft/Fee Pending/Verified/Withdrawn/Lost)
never reached the point of owing tuition.

WHAT GETS GENERATED (v1, kept deliberately simple - see module 16's lesson
about not over-engineering synthetic structure that doesn't add real
signal): one "Tuition Fee" row per admitted applicant for academic_year
2026-27. due_date is anchored to that application's reviewed_at (the date
admission was confirmed) plus a 20-45 day grace window, then clipped to be
at least 3 days before "now" so every row's pay/default outcome is already
decided - this avoids "not due yet" rows with an undefined label. amount_due
is a plausible private-engineering-college first-year tuition instalment
(45,000-85,000 INR).

WHO DEFAULTS: audited first (see comments below) - applicants.annual_income
is NEVER populated by seed_dev_fake_leads.py (always NULL), so it carries no
signal and is not used. parent_occupation IS populated (OCCUPATIONS in that
script) and is a defensible real-world proxy for repayment reliability, so
default risk here is driven by a NEW, independent per-occupation logit
(OCCUPATION_DEFAULT_RISK below - deliberately not reusing that script's
conversion-oriented OCCUPATIONS weights, which measure a different thing)
plus Gaussian noise. Unconditional on any academic feature (cutoff/marks/
etc), same as module 16's fixed dropout-cohort design - keeps the ML
problem genuinely learnable from parent_occupation rather than accidentally
leaking through some other column.

WHO GETS A MATCHING fee_payments ROW: everyone who did NOT default, with
payment_date = due_date +/- a spread (some pay a bit early, some a bit
late, capped at "now"). Defaulters get no fee_payments row at all - module
18's label is computed later (in the training query) purely as "does a
matching fee_payments row exist", exactly how a real registrar would check.

Safety rules (do not weaken - same as seed_dev_fake_leads.py):
  * DEV ONLY. Uses DEV_SUPABASE_URL/KEY and refuses to run if they are empty
    or equal to the PROD credentials.
  * DRY-RUN BY DEFAULT. Nothing touches the database unless --apply is given.
  * Requires seed_dev_fake_leads.py's data (marked Admitted applicants) to
    already exist in DEV - refuses if none are found.
  * Requires migration 0019 (fee_due_schedule table) applied on DEV first.
  * --delete removes only fee_due_schedule/fee_payments rows belonging to
    marked (seed.example.com) applicants - nothing else.

Usage (from the API repo root, in the conda env):
    python scripts/seed_dev_fee_due_schedule.py                  # dry-run, prints a sample
    python scripts/seed_dev_fee_due_schedule.py --apply
    python scripts/seed_dev_fee_due_schedule.py --delete         # dry-run: counts what would go
    python scripts/seed_dev_fee_due_schedule.py --delete --apply # really delete the fake rows

NOTE ON REALISM: same disclaimer as seed_dev_fake_leads.py - the occupation
-> default-risk mapping is a hand-set, plausible assumption, NOT calibrated
to any real repayment data. Fine for building/testing the ML pipeline; do
not quote model accuracy from this data as if it were real.
"""
import argparse
import math
import random
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

MARKER_DOMAIN = "seed.example.com"
IST = timezone(timedelta(hours=5, minutes=30))
ACADEMIC_YEAR = "2026-27"

# Independent of seed_dev_fake_leads.py's OCCUPATIONS conversion weights -
# see the module docstring for why. Positive = higher default-risk logit.
# Government Employee (steady salary) is the reference/lowest-risk group;
# Daily Wage (least predictable income) is the highest.
OCCUPATION_DEFAULT_RISK = {
    "Government Employee": -0.6,
    "Private Employee": -0.1,
    "Business": -0.3,
    "Farmer": 0.5,
    "Daily Wage": 0.9,
    "Other": 0.2,
}
DEFAULT_RISK_BASE = -0.2  # centers the population's average default rate roughly mid-range
AMOUNT_DUE_RANGE = (45000, 85000)
DUE_DATE_GRACE_DAYS = (20, 45)  # after reviewed_at
PAYMENT_SPREAD_DAYS = (-10, 15)  # relative to due_date, for those who pay


def clip(x, lo, hi):
    return max(lo, min(hi, x))


def sigmoid(z):
    return 1 / (1 + math.exp(-z))


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


def fetch_admitted_marked_applicants(client):
    """Marked (seed.example.com) applicants with an Admitted application,
    plus the fields the fee-default logit and due-date anchor need.
    Paginated the same way fetch_marked() is in seed_dev_fake_leads.py."""
    out, start, page = [], 0, 1000
    cols = "id,applicant_id,reviewed_at,applicants!inner(id,email,parent_occupation)"
    while True:
        res = (
            client.table("applications")
            .select(cols)
            .eq("application_stage", "Admitted")
            .is_("deleted_at", "null")
            .like("applicants.email", f"%@{MARKER_DOMAIN}")
            .range(start, start + page - 1)
            .execute()
        )
        out.extend(res.data)
        if len(res.data) < page:
            break
        start += page
    return out


def generate(admitted_rows, seed, now_date):
    """Returns (fee_due_schedule_rows, fee_payments_rows). Own rng stream,
    independent of seed_dev_fake_leads.py's - see module docstring."""
    rng = random.Random(seed)
    due_schedule, payments = [], []

    for row in admitted_rows:
        applicant_id = row["applicant_id"]
        occ = (row.get("applicants") or {}).get("parent_occupation") or "Other"
        reviewed_at_raw = row.get("reviewed_at")
        if reviewed_at_raw:
            anchor = datetime.fromisoformat(reviewed_at_raw.replace("Z", "+00:00")).date()
        else:
            anchor = now_date - timedelta(days=60)  # fallback for the rare missing reviewed_at

        due_date = anchor + timedelta(days=rng.randint(*DUE_DATE_GRACE_DAYS))
        due_date = min(due_date, now_date - timedelta(days=3))  # always already-due -> label is defined

        amount_due = round(rng.uniform(*AMOUNT_DUE_RANGE) / 500) * 500

        due_schedule.append(dict(
            applicant_id=applicant_id,
            fee_component="Tuition Fee",
            academic_year=ACADEMIC_YEAR,
            amount_due=float(amount_due),
            due_date=due_date.isoformat(),
        ))

        logit = DEFAULT_RISK_BASE + OCCUPATION_DEFAULT_RISK.get(occ, 0.0) + rng.gauss(0, 0.4)
        defaulted = rng.random() < sigmoid(logit)

        if not defaulted:
            payment_date = due_date + timedelta(days=rng.randint(*PAYMENT_SPREAD_DAYS))
            payment_date = min(payment_date, now_date)
            payments.append(dict(
                applicant_id=applicant_id,
                fee_component="Tuition Fee",
                amount=float(amount_due),
                payment_mode=rng.choice(["Online", "Cheque", "Cash", "DD"]),
                payment_date=payment_date.isoformat(),
                academic_year=ACADEMIC_YEAR,
                remarks="Seed data (fake) - see scripts/seed_dev_fee_due_schedule.py",
            ))

    return due_schedule, payments


def validate_with_api_models(due_schedule, payments):
    from app.models.fee_due_schedule import FeeDueScheduleCreate
    from app.models.fee_payments import FeePaymentCreate
    for row in due_schedule:
        FeeDueScheduleCreate(**row)
    for row in payments:
        FeePaymentCreate(**row)


def print_report(due_schedule, payments, show):
    defaulted = len(due_schedule) - len(payments)
    print(f"\nGenerated {len(due_schedule)} fee_due_schedule rows, {len(payments)} matching fee_payments "
          f"({defaulted} defaulted, {defaulted / len(due_schedule):.1%})" if due_schedule else "Nothing to generate.")
    for row in due_schedule[:show]:
        print(f"  due: applicant={row['applicant_id']}  amount={row['amount_due']}  due_date={row['due_date']}")


def marked_applicant_ids(client):
    out, start, page = [], 0, 1000
    while True:
        res = client.table("applicants").select("id").like("email", f"%@{MARKER_DOMAIN}").range(start, start + page - 1).execute()
        out.extend(r["id"] for r in res.data)
        if len(res.data) < page:
            break
        start += page
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=42, help="same seed -> same data")
    ap.add_argument("--show", type=int, default=10)
    ap.add_argument("--apply", action="store_true", help="really write (or delete); default is dry-run")
    ap.add_argument("--delete", action="store_true", help="remove the marked fake fee rows")
    ap.add_argument("--force", action="store_true", help="seed even if fake fee rows already exist")
    args = ap.parse_args()

    if args.delete:
        client = get_dev_client()
        ids = marked_applicant_ids(client)
        print(f"Marked applicants in DEV: {len(ids)}")
        if not args.apply:
            print("Dry-run: nothing deleted. Add --apply to delete fee_due_schedule/fee_payments for these applicants.")
            return
        deleted_payments = deleted_due = 0
        for part in chunks(ids, 200):
            if not part:
                continue
            r1 = client.table("fee_payments").delete().in_("applicant_id", part).execute()
            r2 = client.table("fee_due_schedule").delete().in_("applicant_id", part).execute()
            deleted_payments += len(r1.data or [])
            deleted_due += len(r2.data or [])
        print(f"Deleted fee_payments: {deleted_payments}, fee_due_schedule: {deleted_due}")
        return

    client = get_dev_client()
    admitted_rows = fetch_admitted_marked_applicants(client)
    print(f"Found {len(admitted_rows)} marked Admitted applicants in DEV.")
    if not admitted_rows:
        sys.exit("REFUSING: no marked Admitted applicants found. Run seed_dev_fake_leads.py --apply first.")

    now_date = datetime.now(IST).date()
    due_schedule, payments = generate(admitted_rows, args.seed, now_date)
    validate_with_api_models(due_schedule, payments)
    print("All generated rows pass the API's own response models (no 500 risk).")
    print_report(due_schedule, payments, args.show)
    if not args.apply:
        print("\nDRY-RUN: nothing written. Re-run with --apply to write to DEV.")
        return

    existing = client.table("fee_due_schedule").select("id", count="exact").in_(
        "applicant_id", [r["applicant_id"] for r in admitted_rows]
    ).limit(1).execute().count or 0
    if existing and not args.force:
        sys.exit(f"REFUSING: {existing} fake fee_due_schedule rows already exist in DEV. Use --delete --apply first, or --force.")

    for part in chunks(due_schedule):
        client.table("fee_due_schedule").insert(part).execute()
    print(f"Inserted fee_due_schedule: {len(due_schedule)}")

    for part in chunks(payments):
        client.table("fee_payments").insert(part).execute()
    print(f"Inserted fee_payments: {len(payments)}")

    print(f"\nWROTE to DEV: fee_due_schedule={len(due_schedule)}, fee_payments={len(payments)}, "
          f"defaults={len(due_schedule) - len(payments)}")


if __name__ == "__main__":
    main()
