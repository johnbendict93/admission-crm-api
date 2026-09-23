"""Plants a small number of deliberately-suspicious FAKE leads into the DEV
`leads` table, for module 22 (Fraud Anomaly Detection).

WHY A SEPARATE, ADDITIVE-ONLY SCRIPT: same reasoning as
seed_dev_fee_due_schedule.py / seed_dev_enquiry_monthly_history.py - this
never touches or regenerates the ~500 leads seed_dev_fake_leads.py already
wrote, it only ADDS new rows. Safe to re-run (with --delete --apply first)
without disturbing anything the other ML modules were trained on.

WHAT GETS PLANTED (28 leads total, ~5% of the existing ~500-lead
population - deliberately a MINORITY, matching a real fraud rate, not a
50/50 mix an anomaly detector would never see in production):

  * duplicate-phone (8 leads, 4 pairs) - two leads sharing the exact same
    phone number. The organic generator actively prevents this (a
    `used_phones` set) - any duplicate at all is an unambiguous signal.
  * bot-timestamp (8 leads, 2 clusters of 4) - leads sharing the exact
    same created_at, to the second. The organic generator draws each
    lead's time independently and continuously - an exact multi-lead match
    is astronomically unlikely to happen by chance.
  * geo-mismatch (6 leads) - a `school` string whose embedded town belongs
    to a DIFFERENT district than the one stated on the lead (e.g. district
    "Madurai" with a school actually located in Chennai).
  * implausible-marks (6 leads) - a `marks`/`score` combination far
    outside how those two columns normally relate (very low marks with a
    very high score, or the reverse) - a joint-distribution outlier.

Every other field (name, source, course_interest, parent info) is
generated to look otherwise ordinary, so the ONLY anomalous signal on each
planted lead is the one dimension being tested - keeps
ml/train_fraud_detection_model.py's evaluation clean (which fraud pattern
did the model actually catch, and which didn't it).

MARKING: email is `fraud.<type-slug>.<i>@seed.example.com` - still ends in
the shared MARKER_DOMAIN (so a full `seed_dev_fake_leads.py --delete
--apply` wipe still catches these rows too, same as every other fake row
in this repo), but with a distinguishing "fraud." prefix this script's own
--delete can target on its own, without needing the ground-truth file to
still exist. assigned_to is left unset (None) and status is "New" for
every planted lead - deliberately so these never appear in module 21's
live "leads for telecaller X to call" ranking (that query filters on
assigned_to; see app/services/ml_lead_ranking_service.py).

CROSS-MODULE SAFETY: unlike every other planted-fraud consideration above,
one thing needed an actual code change, not just a naming convention -
ml/train_conversion_model.py's leads query had NO filter at all (trains on
literally every row in the table), so module 13's conversion model would
otherwise have quietly absorbed these 28 deliberately-weird rows as
ordinary negative examples. Fixed by adding `WHERE email NOT LIKE
'fraud.%'` to that query - module 22's own training script
(ml/train_fraud_detection_model.py) is the ONE place that deliberately
INCLUDES these rows, since an anomaly detector needs anomalies actually
present in its training population to have anything to separate from the
rest.

GROUND TRUTH (eval-only, never a DB column, never a training label): on
--apply, after inserting, this script reads back the newly-inserted rows
by their fraud. email prefix and writes ml/eval/fraud_ground_truth.json
(id -> fraud_type + description). ml/train_fraud_detection_model.py reads
this file ONLY to report how many planted frauds got flagged - it is never
fed into the model itself. Gitignored (ml/eval/) - it holds live DEV row
ids, meaningless the moment leads get regenerated.

Safety rules (same shape as every other seed_dev_*.py script):
  * DEV ONLY. Uses DEV_SUPABASE_URL/KEY and refuses to run if they are
    empty or equal to the PROD credentials.
  * DRY-RUN BY DEFAULT. Nothing touches the database unless --apply.
  * --delete removes only rows with email LIKE 'fraud.%@seed.example.com'
    and clears the local ground-truth file - nothing else.
  * Requires scripts/seed_dev_fake_leads.py's data (marked leads) to
    already exist in DEV, so there's a real population for these to hide
    among - refuses if none are found.

Usage (from the API repo root, in the conda env):
    python scripts/seed_dev_fraud_leads.py                  # dry-run, prints all 28 rows
    python scripts/seed_dev_fraud_leads.py --apply
    python scripts/seed_dev_fraud_leads.py --delete         # dry-run: counts what would go
    python scripts/seed_dev_fraud_leads.py --delete --apply # really delete the fraud rows

NOTE ON REALISM: these are hand-designed fraud patterns chosen to be
UNAMBIGUOUS (so this module's evaluation is clean), not a simulation of
every way real fraud actually looks. Fine for building/testing the
anomaly-detection pipeline; do not present recall on this planted set as a
real-world fraud-catch rate.
"""
import argparse
import json
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

MARKER_DOMAIN = "seed.example.com"
IST = timezone(timedelta(hours=5, minutes=30))

GROUND_TRUTH_PATH = Path(__file__).resolve().parent.parent / "ml" / "eval" / "fraud_ground_truth.json"

# Small, independent name/source/course pools - just enough variety that
# planted leads don't all look identical on the fields that AREN'T the
# fraud signal being tested. Not the full generator's pools (unnecessary
# here - name/source/course are not fraud-detection features at all, see
# ml/features_fraud_detection.py).
NAMES = ["Arun Kumar", "Divya Priya", "Karthik Raj", "Priya Devi", "Suresh Babu", "Lakshmi Bala",
         "Vignesh Kannan", "Sowmiya Rani"]
SOURCES = ["Walk-in", "Website", "Referral", "Social Media"]
COURSES = ["B.E. Computer Science", "B.E. Electronics & Communication", "B.E. Mechanical", "Other"]
PARENT_OCCS = ["Government Employee", "Private Employee", "Business"]

# Independent copy of scripts/seed_dev_fake_leads.py's DISTRICTS town
# lists - real Tamil Nadu geography, not a formula. Keep in sync if that
# script's town lists change (same convention as every other independent-
# copy constant in this repo, e.g. ml/pipeline_forecast.py's MONTH_W).
DISTRICT_TOWNS = {
    "Chennai": ["Adyar", "T. Nagar", "Ambattur", "Perambur", "Velachery", "Kolathur"],
    "Kancheepuram": ["Sriperumbudur", "Walajabad", "Uthiramerur", "Kancheepuram"],
    "Villupuram": ["Gingee", "Tindivanam", "Vikravandi", "Villupuram"],
    "Cuddalore": ["Chidambaram", "Neyveli", "Panruti", "Cuddalore"],
    "Vellore": ["Katpadi", "Gudiyatham", "Arcot", "Vellore"],
    "Coimbatore": ["Pollachi", "Mettupalayam", "Singanallur"],
    "Madurai": ["Melur", "Thirumangalam", "Usilampatti"],
    "Tiruchirappalli": ["Srirangam", "Lalgudi", "Musiri"],
    "Salem": ["Attur", "Omalur", "Mettur"],
    "Tirunelveli": ["Palayamkottai", "Ambasamudram"],
    "Erode": ["Bhavani", "Gobichettipalayam"],
    "Thanjavur": ["Kumbakonam", "Papanasam", "Orathanadu"],
    "Namakkal": ["Rasipuram", "Tiruchengode"],
    "Dindigul": ["Palani", "Oddanchatram"],
    "Other": ["Tiruvannamalai", "Krishnagiri", "Dharmapuri", "Ariyalur"],
}
SCHOOL_KIND = "Govt. Hr. Sec. School"


def clip(x, lo, hi):
    return max(lo, min(hi, x))


def base_lead(rng, i):
    """Common, otherwise-ordinary-looking fields shared by every planted
    lead, before the fraud-specific fields are overlaid."""
    name = rng.choice(NAMES)
    return {
        "name": name,
        "parent_name": rng.choice(NAMES),
        "parent_occupation": rng.choice(PARENT_OCCS),
        "source": rng.choice(SOURCES),
        "course_interest": rng.choice(COURSES),
        "status": "New",
        "assigned_to": None,  # deliberately unassigned - see module docstring
        "score": int(clip(rng.gauss(45, 15), 5, 98)),
    }


def random_phone(rng, used):
    while True:
        p = "5" + "".join(str(rng.randint(0, 9)) for _ in range(9))
        if p not in used:
            used.add(p)
            return p


def random_created_at(rng, today):
    d = today - timedelta(days=rng.randint(1, 60))
    return datetime(d.year, d.month, d.day, rng.randint(9, 18), rng.randint(0, 59), rng.randint(0, 59), tzinfo=IST)


def normal_school_district(rng):
    district = rng.choice(list(DISTRICT_TOWNS))
    town = rng.choice(DISTRICT_TOWNS[district])
    return district, f"{SCHOOL_KIND}, {town}"


def generate(seed: int, today) -> list[dict]:
    rng = random.Random(seed)
    used_phones: set[str] = set()
    rows = []

    # --- duplicate-phone: 4 pairs, 8 leads ---
    for pair in range(4):
        shared_phone = random_phone(rng, used_phones)
        for k in range(2):
            i = pair * 2 + k
            row = base_lead(rng, i)
            district, school = normal_school_district(rng)
            row.update(
                email=f"fraud.duplicate-phone.{i}@{MARKER_DOMAIN}",
                phone=shared_phone,
                parent_phone=random_phone(rng, used_phones),
                district=district, school=school,
                marks=round(clip(rng.gauss(74, 13), 45, 99), 1),
                created_at=random_created_at(rng, today).isoformat(),
                _fraud_type="duplicate-phone",
                _fraud_reason=f"shares phone {shared_phone} with another lead in this same planted pair",
            )
            rows.append(row)

    # --- bot-timestamp: 2 clusters of 4, 8 leads ---
    for cluster in range(2):
        shared_ts = random_created_at(rng, today)
        for k in range(4):
            i = cluster * 4 + k
            row = base_lead(rng, i)
            district, school = normal_school_district(rng)
            row.update(
                email=f"fraud.bot-timestamp.{i}@{MARKER_DOMAIN}",
                phone=random_phone(rng, used_phones),
                parent_phone=random_phone(rng, used_phones),
                district=district, school=school,
                marks=round(clip(rng.gauss(74, 13), 45, 99), 1),
                created_at=shared_ts.isoformat(),
                _fraud_type="bot-timestamp",
                _fraud_reason=f"shares created_at {shared_ts.isoformat()} (to the second) with 3 other planted leads",
            )
            rows.append(row)

    # --- geo-mismatch: 6 leads ---
    for i in range(6):
        row = base_lead(rng, i)
        real_district = rng.choice(list(DISTRICT_TOWNS))
        # pick a school from a DIFFERENT district than the one claimed
        wrong_district = rng.choice([d for d in DISTRICT_TOWNS if d != real_district])
        wrong_town = rng.choice(DISTRICT_TOWNS[wrong_district])
        row.update(
            email=f"fraud.geo-mismatch.{i}@{MARKER_DOMAIN}",
            phone=random_phone(rng, used_phones),
            parent_phone=random_phone(rng, used_phones),
            district=real_district, school=f"{SCHOOL_KIND}, {wrong_town}",
            marks=round(clip(rng.gauss(74, 13), 45, 99), 1),
            created_at=random_created_at(rng, today).isoformat(),
            _fraud_type="geo-mismatch",
            _fraud_reason=f"district={real_district} but school is in {wrong_town} ({wrong_district})",
        )
        rows.append(row)

    # --- implausible-marks: 6 leads (alternating low-marks/high-score and high-marks/low-score) ---
    for i in range(6):
        row = base_lead(rng, i)
        district, school = normal_school_district(rng)
        if i % 2 == 0:
            marks, score = round(rng.uniform(20, 35), 1), int(rng.uniform(85, 98))
        else:
            marks, score = round(rng.uniform(92, 99), 1), int(rng.uniform(5, 20))
        row.update(
            email=f"fraud.implausible-marks.{i}@{MARKER_DOMAIN}",
            phone=random_phone(rng, used_phones),
            parent_phone=random_phone(rng, used_phones),
            district=district, school=school,
            marks=marks, score=score,
            created_at=random_created_at(rng, today).isoformat(),
            _fraud_type="implausible-marks",
            _fraud_reason=f"marks={marks} but score={score} - joint outlier, doesn't fit the normal marks-score relationship",
        )
        rows.append(row)

    return rows


def print_report(rows):
    by_type: dict[str, list[dict]] = {}
    for r in rows:
        by_type.setdefault(r["_fraud_type"], []).append(r)
    print(f"\nGenerated {len(rows)} fraud leads across {len(by_type)} types:")
    for fraud_type, group in by_type.items():
        print(f"\n  {fraud_type} ({len(group)} leads):")
        for r in group[:4]:
            print(f"    {r['email']:38} phone={r['phone']}  district={r['district']:14}  "
                  f"marks={r['marks']:5}  score={r['score']:3}  created_at={r['created_at']}")
        if len(group) > 4:
            print(f"    ... and {len(group) - 4} more")


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
    ap.add_argument("--delete", action="store_true", help="remove the fraud rows (email LIKE 'fraud.%@seed.example.com')")
    ap.add_argument("--force", action="store_true", help="seed even if fraud rows already exist")
    args = ap.parse_args()

    if args.delete:
        client = get_dev_client()
        existing = client.table("leads").select("id", count="exact").like("email", f"fraud.%@{MARKER_DOMAIN}").limit(1).execute().count or 0
        print(f"Planted fraud leads in DEV: {existing}")
        if not args.apply:
            print("Dry-run: nothing deleted. Add --apply to delete the fraud leads.")
            return
        result = client.table("leads").delete().like("email", f"fraud.%@{MARKER_DOMAIN}").execute()
        print(f"Deleted {len(result.data or [])} fraud leads")
        if GROUND_TRUTH_PATH.exists():
            GROUND_TRUTH_PATH.unlink()
            print(f"Removed {GROUND_TRUTH_PATH}")
        return

    today = datetime.now(IST).date()
    rows = generate(args.seed, today)
    print_report(rows)
    if not args.apply:
        print("\nDRY-RUN: nothing written. Re-run with --apply to write to DEV.")
        return

    client = get_dev_client()
    marked_count = client.table("leads").select("id", count="exact").like("email", "%@" + MARKER_DOMAIN).limit(1).execute().count or 0
    if not marked_count:
        sys.exit("REFUSING: no marked leads found in DEV - run scripts/seed_dev_fake_leads.py --apply first, "
                  "so these fraud leads have a real population to hide among.")

    existing_fraud = client.table("leads").select("id", count="exact").like("email", f"fraud.%@{MARKER_DOMAIN}").limit(1).execute().count or 0
    if existing_fraud and not args.force:
        sys.exit(f"REFUSING: {existing_fraud} fraud leads already exist in DEV. Use --delete --apply first, or --force.")

    insert_rows = [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]
    for part in chunks(insert_rows):
        client.table("leads").insert(part).execute()
    print(f"Inserted fraud leads: {len(insert_rows)}")

    # Read back by the fraud. email prefix (not the insert response) so
    # ground truth is built from what's actually in the DB, regardless of
    # any assumption about insert-response row ordering.
    inserted = client.table("leads").select("id,email").like("email", f"fraud.%@{MARKER_DOMAIN}").execute().data
    email_to_planted = {r["email"]: r for r in rows}
    ground_truth = {}
    for row in inserted:
        planted = email_to_planted.get(row["email"])
        if not planted:
            continue  # a fraud lead from a PRIOR run under a different seed - not ours to label
        ground_truth[row["id"]] = {
            "fraud_type": planted["_fraud_type"],
            "reason": planted["_fraud_reason"],
            "email": row["email"],
        }

    GROUND_TRUTH_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(GROUND_TRUTH_PATH, "w", encoding="utf-8") as f:
        json.dump(ground_truth, f, indent=2)
    print(f"Wrote ground truth for {len(ground_truth)} leads to {GROUND_TRUTH_PATH}")


if __name__ == "__main__":
    main()
