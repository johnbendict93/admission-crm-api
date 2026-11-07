"""
DEV ONLY. Adds realistic, explainable "it depends on the student" patterns to
the synthetic dev data, so the per-lead AI predictions stop giving everyone
the same answer (Nov 2026).

Why: the original generator (scripts/seed_dev_fake_leads.py) gave every
telecaller ONE fixed skill bonus and made every evening call slightly better.
The models learned exactly that - "Telecaller A is best for everyone" and
"always call at 8 PM". Real call-centre data depends on the lead.

What it changes (seed-marked rows only: leads.email LIKE '%@seed.example.com',
plus the followups of those leads). Nothing else is touched - names, phones,
statuses, counts, funnel and response/notes text all stay exactly as they are.

  1. leads.assigned_to - telecaller specialties:
        Telecaller D: Farmer / Daily Wage families (rapport with first-gen students)
        Telecaller A: Computer Science / AI & Data Science / IT courses
        Telecaller B: Mechanical / Civil / Automobile courses
        Telecaller C: ECE / EEE courses
     Enrolled leads get their specialist 75% of the time, Lost leads only 25%
     of the time; open leads (New/Contacted/Visited) are assigned at random.
  2. followups.called_by = the lead's assigned_to (keeps call logs consistent).
  3. followups.call_time hour - best reachable window by parent occupation:
        Farmer 09-10, Business 13-15, Government Employee 17-19,
        Private Employee 19-20, Daily Wage 20, Other 11-13
     Calls whose response was POSITIVE are moved into that window 70% of the
     time; other calls get a uniformly random hour 9-20. Minutes are kept.

Safety: refuses to run unless DEV_DATABASE_URL is set and differs from
PROD_DATABASE_URL; dry-run by default (prints what would change); --apply
writes in ONE transaction and first saves the old values to
_local_backups/enrich_dev_ml_patterns_<timestamp>.json (gitignored).
--undo <that file> restores them.

    conda activate admission-crm-api
    python scripts/enrich_dev_ml_patterns.py            # dry run
    python scripts/enrich_dev_ml_patterns.py --apply    # really write
"""
import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import psycopg2  # noqa: E402
import psycopg2.extras  # noqa: E402

from app.core.config import settings  # noqa: E402
from ml.features_followup_timing import CANDIDATE_HOURS, make_label  # noqa: E402

SEED = 20261107
MARKER = "%@seed.example.com"
TELECALLERS = ["Telecaller A", "Telecaller B", "Telecaller C", "Telecaller D"]
OCCUPATION_WINDOWS = {
    "Farmer": [9, 10],
    "Business": [13, 14, 15],
    "Government Employee": [17, 18, 19],
    "Private Employee": [19, 20],
    "Daily Wage": [20],
    "Other": [11, 12, 13],
}
SPECIALIST_IF_ENROLLED = 0.75
SPECIALIST_IF_LOST = 0.25
POSITIVE_IN_WINDOW = 0.70


def specialist_for(lead: dict) -> str | None:
    occ = (lead.get("parent_occupation") or "").strip()
    course = (lead.get("course_interest") or "").lower()
    if occ in ("Farmer", "Daily Wage"):
        return "Telecaller D"
    if any(k in course for k in ("computer", "ai ", "ai&", "data science", "information technology", " it")):
        return "Telecaller A"
    if any(k in course for k in ("mechanical", "civil", "automobile")):
        return "Telecaller B"
    if any(k in course for k in ("electronics", "electrical", "ece", "eee")):
        return "Telecaller C"
    return None


def pick_telecaller(rng: random.Random, lead: dict) -> str:
    status = lead.get("status")
    spec = specialist_for(lead)
    if spec is None or status not in ("Enrolled", "Lost"):
        return rng.choice(TELECALLERS)
    p = SPECIALIST_IF_ENROLLED if status == "Enrolled" else SPECIALIST_IF_LOST
    if rng.random() < p:
        return spec
    return rng.choice([t for t in TELECALLERS if t != spec])


def new_call_time(rng: random.Random, old: str | None, occupation: str | None, positive: bool) -> str:
    minute = "00"
    if old and ":" in str(old):
        minute = str(old).split(":")[1][:2].zfill(2)
    window = OCCUPATION_WINDOWS.get((occupation or "").strip(), OCCUPATION_WINDOWS["Other"])
    if positive and rng.random() < POSITIVE_IN_WINDOW:
        hour = rng.choice(window)
    else:
        hour = rng.choice(CANDIDATE_HOURS)
    return f"{hour:02d}:{minute}"


def connect():
    dev, prod = settings.DEV_DATABASE_URL, settings.PROD_DATABASE_URL
    if not dev:
        sys.exit("DEV_DATABASE_URL not set - aborting.")
    if prod and dev.strip() == prod.strip():
        sys.exit("REFUSING: DEV_DATABASE_URL equals PROD_DATABASE_URL.")
    return psycopg2.connect(dev)


def load(cur):
    cur.execute(
        "SELECT id, status, course_interest, parent_occupation, assigned_to FROM public.leads "
        "WHERE email LIKE %s AND deleted_at IS NULL ORDER BY id;", (MARKER,))
    leads = [dict(r) for r in cur.fetchall()]
    cur.execute(
        "SELECT f.id, f.lead_id, f.called_by, f.call_time, f.response FROM public.followups f "
        "JOIN public.leads l ON l.id = f.lead_id "
        "WHERE l.email LIKE %s AND l.deleted_at IS NULL AND f.deleted_at IS NULL ORDER BY f.id;", (MARKER,))
    followups = [dict(r) for r in cur.fetchall()]
    return leads, followups


def plan(leads, followups):
    rng = random.Random(SEED)
    lead_updates = {l["id"]: pick_telecaller(rng, l) for l in leads}
    by_id = {l["id"]: l for l in leads}
    fu_updates = {}
    for f in followups:
        lead = by_id[f["lead_id"]]
        fu_updates[f["id"]] = (
            lead_updates[lead["id"]],
            new_call_time(rng, f.get("call_time"), lead.get("parent_occupation"), make_label(f.get("response")) == 1),
        )
    return lead_updates, fu_updates


def report(leads, followups, lead_updates, fu_updates):
    by_id = {l["id"]: l for l in leads}
    print(f"Seed-marked leads: {len(leads)}   their followups: {len(followups)}")
    print("\nEnrolled share by telecaller AFTER (resolved leads only) - specialist vs not:")
    tally = defaultdict(lambda: [0, 0])
    for lid, tc in lead_updates.items():
        l = by_id[lid]
        if l["status"] in ("Enrolled", "Lost"):
            key = "specialist" if specialist_for(l) == tc else "non-specialist"
            tally[key][0] += l["status"] == "Enrolled"
            tally[key][1] += 1
    for k, (e, n) in tally.items():
        print(f"  {k:15} {e}/{n} enrolled ({e / n:.0%})" if n else f"  {k}: none")
    print("\nNew telecaller load:", dict(Counter(lead_updates.values())))
    pos_in = pos = 0
    for f in followups:
        if make_label(f.get("response")) == 1:
            pos += 1
            occ = by_id[f["lead_id"]].get("parent_occupation")
            hour = int(fu_updates[f["id"]][1][:2])
            pos_in += hour in OCCUPATION_WINDOWS.get((occ or "").strip(), OCCUPATION_WINDOWS["Other"])
    if pos:
        print(f"Positive calls inside their family's best window AFTER: {pos_in}/{pos} ({pos_in / pos:.0%})")


def apply(conn, leads, followups, lead_updates, fu_updates):
    backup_dir = ROOT / "_local_backups"
    backup_dir.mkdir(exist_ok=True)
    path = backup_dir / f"enrich_dev_ml_patterns_{datetime.now():%Y%m%d_%H%M%S}.json"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"leads": [{"id": str(l["id"]), "assigned_to": l["assigned_to"]} for l in leads],
                   "followups": [{"id": str(f["id"]), "called_by": f["called_by"], "call_time": f["call_time"]}
                                 for f in followups]}, fh, indent=1)
    print(f"\nBackup of old values saved to {path}")
    with conn, conn.cursor() as cur:
        psycopg2.extras.execute_batch(cur, "UPDATE public.leads SET assigned_to=%s WHERE id=%s;",
                                      [(tc, lid) for lid, tc in lead_updates.items()], page_size=200)
        psycopg2.extras.execute_batch(cur, "UPDATE public.followups SET called_by=%s, call_time=%s WHERE id=%s;",
                                      [(tc, ct, fid) for fid, (tc, ct) in fu_updates.items()], page_size=200)
    print(f"Applied: {len(lead_updates)} leads, {len(fu_updates)} followups updated (one transaction).")


def undo(conn, backup_file):
    data = json.loads(Path(backup_file).read_text(encoding="utf-8"))
    with conn, conn.cursor() as cur:
        psycopg2.extras.execute_batch(cur, "UPDATE public.leads SET assigned_to=%s WHERE id=%s;",
                                      [(r["assigned_to"], r["id"]) for r in data["leads"]], page_size=200)
        psycopg2.extras.execute_batch(cur, "UPDATE public.followups SET called_by=%s, call_time=%s WHERE id=%s;",
                                      [(r["called_by"], r["call_time"], r["id"]) for r in data["followups"]],
                                      page_size=200)
    print(f"Restored {len(data['leads'])} leads and {len(data['followups'])} followups from {backup_file}.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="really write (default is a dry run)")
    ap.add_argument("--undo", metavar="BACKUP_JSON", help="restore old values from a backup file")
    args = ap.parse_args()
    conn = connect()
    try:
        if args.undo:
            undo(conn, args.undo)
            return
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            leads, followups = load(cur)
        if not leads:
            sys.exit("No seed-marked leads found in dev - nothing to do.")
        lead_updates, fu_updates = plan(leads, followups)
        report(leads, followups, lead_updates, fu_updates)
        if args.apply:
            apply(conn, leads, followups, lead_updates, fu_updates)
        else:
            print("\nDRY RUN - nothing written. Re-run with --apply to write.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
