"""Backfills richer call-note text onto EXISTING dev followups, for module
19 (NLP Call Sentiment Analyzer).

WHY A SEPARATE SCRIPT, NOT A REGENERATE: build_followups_and_schedules()
in seed_dev_fake_leads.py now builds notes via build_note() (a much richer
combinatorial bank - see that script's comment on NOTE_OPENERS/DETAILS/
CLOSERS), but that only helps FUTURE --apply runs. The ~1600 followup rows
already in dev were written with the old 3-template NOTES_POS/NEU/NEG and
would need a full --delete --apply of seed_dev_fake_leads.py to pick up
the new bank - which would regenerate leads/applicants/applications too,
and since fee_due_schedule.applicant_id is ON DELETE CASCADE from
applicants (migration 0019), that would silently WIPE module 18's already-
seeded fee_due_schedule/fee_payments data along with it. This script
instead does a plain UPDATE of followups.notes in place, for rows that
already exist - lead_id/response/call_date/etc are all left untouched, and
nothing outside the followups table is touched at all.

HOW THE LABEL WORKS: `response` is a short categorical phrase drawn from a
small fixed set (RESPONSE_POS/NEU/NEG in seed_dev_fake_leads.py) - since
that set is small and exhaustive, which bucket (pos/neu/neg) a followup
belongs to can be recovered exactly from its `response` text (see
RESPONSE_TO_BUCKET below). That bucket is used both to pick a matching new
note here AND, at training time (ml/features_call_sentiment.py), to derive
the sentiment label - so notes and label are always consistent.

Safety rules (same spirit as seed_dev_fake_leads.py / seed_dev_fee_due_schedule.py):
  * DEV ONLY. Uses DEV_SUPABASE_URL/KEY and refuses to run if empty or
    equal to the PROD credentials.
  * DRY-RUN BY DEFAULT. Nothing written unless --apply is given.
  * Only touches followups belonging to marked (seed.example.com) leads -
    matched via lead_id, same join pattern as seed_dev_fake_leads.py's
    --delete flow.
  * UPDATEs notes only - no inserts, no deletes, no other columns touched.

Usage (from the API repo root, in the conda env):
    python scripts/enrich_dev_followup_notes.py                  # dry-run, prints a sample
    python scripts/enrich_dev_followup_notes.py --apply
"""
import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.seed_dev_fake_leads import (
    MARKER_DOMAIN,
    RESPONSE_NEG,
    RESPONSE_NEU,
    RESPONSE_POS,
    build_note,
    chunks,
    get_dev_client,
)

RESPONSE_TO_BUCKET = {}
for _r in RESPONSE_POS:
    RESPONSE_TO_BUCKET[_r] = "pos"
for _r in RESPONSE_NEU:
    RESPONSE_TO_BUCKET[_r] = "neu"
for _r in RESPONSE_NEG:
    RESPONSE_TO_BUCKET[_r] = "neg"


def fetch_marked_followups(client):
    """followups has no email column of its own - matched via lead_id back
    to marked leads, same as seed_dev_fake_leads.py's --delete flow.
    Paginated the same way fetch_marked() is there."""
    lead_ids = []
    start, page = 0, 1000
    while True:
        res = client.table("leads").select("id").like("email", f"%@{MARKER_DOMAIN}").range(start, start + page - 1).execute()
        lead_ids.extend(r["id"] for r in res.data)
        if len(res.data) < page:
            break
        start += page

    out = []
    for part in chunks(lead_ids, 200):
        if not part:
            continue
        start2, page2 = 0, 1000
        while True:
            res = (
                client.table("followups")
                .select("id,response,notes")
                .in_("lead_id", part)
                .range(start2, start2 + page2 - 1)
                .execute()
            )
            out.extend(res.data)
            if len(res.data) < page2:
                break
            start2 += page2
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--show", type=int, default=10)
    ap.add_argument("--apply", action="store_true", help="really write; default is dry-run")
    args = ap.parse_args()

    client = get_dev_client()
    rows = fetch_marked_followups(client)
    print(f"Found {len(rows)} followups on marked leads in DEV.")
    if not rows:
        sys.exit("REFUSING: no marked followups found. Run seed_dev_fake_leads.py --apply first.")

    unrecognized = [r for r in rows if r["response"] not in RESPONSE_TO_BUCKET]
    if unrecognized:
        print(f"WARNING: {len(unrecognized)} followups have a response text not in the known RESPONSE_POS/NEU/NEG "
              f"set - these will be skipped (left unchanged). Example: {unrecognized[0]['response']!r}")

    rng = random.Random(args.seed)
    updates = []
    for row in rows:
        bucket = RESPONSE_TO_BUCKET.get(row["response"])
        if bucket is None:
            continue
        new_note = build_note(rng, bucket)
        updates.append({"id": row["id"], "old_notes": row["notes"], "new_notes": new_note})

    print(f"\n{len(updates)} followups will get a new note (out of {len(rows)} total).")
    for u in updates[:args.show]:
        print(f"  id={u['id']}")
        print(f"    old: {u['old_notes']!r}")
        print(f"    new: {u['new_notes']!r}")

    if not args.apply:
        print("\nDRY-RUN: nothing written. Re-run with --apply to write to DEV.")
        return

    for u in updates:
        client.table("followups").update({"notes": u["new_notes"]}).eq("id", u["id"]).execute()
    print(f"\nUpdated notes on {len(updates)} followups in DEV.")


if __name__ == "__main__":
    main()
