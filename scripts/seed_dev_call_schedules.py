"""
Seeds 2-3 dev call_schedules rows via the SAME write path the Streamlit
app uses (supabase-py .table().insert().execute() over PostgREST),
with a payload shape that exactly matches what
dce_crm/pages/6_Scheduling_Visits_Telecallers.py actually sends:

    dt = datetime.combine(sched_date, sched_time)
    insert_schedule({
        "lead_id": ...,
        "scheduled_by": ...,
        "scheduled_time": dt.isoformat(),   # naive, no offset
        "status": "Pending"
    })

Deliberately does NOT reuse dce_crm's own get_client()/insert_schedule(),
because dce_crm's .streamlit/secrets.toml SUPABASE_URL points at PROD
(agfmeefnfzsrpyzwejtt.supabase.co), confirmed against the API's .env.
This script hits DEV_SUPABASE_URL/DEV_SUPABASE_KEY from this repo's own
.env instead - same call shape, same field types, same naive-local-time
format, correct target.

Marked clearly as test data via scheduled_by="[SEED] Test Counselor" so
it's unambiguous in any dashboard/report, and never confusable with a
real counselor entry.

Usage:
    python seed_dev_call_schedules.py
"""
import sys
from pathlib import Path
from datetime import date, datetime, time, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.core.config import settings  # noqa: E402
from supabase import create_client

client = create_client(settings.DEV_SUPABASE_URL, settings.DEV_SUPABASE_KEY)

# Two real dev leads (confirmed via check_dev_leads_for_seed.py)
LEAD_A = "6720759d-4fd7-4212-89c9-dc6898bb1fa6"  # Test Lead One
LEAD_B = "c4ad0d7b-367b-4a07-a907-5e78c438188c"  # Test Lead Two

today = date.today()

seed_rows = [
    # (lead_id, date, time) - spread across morning / afternoon / evening
    (LEAD_A, today + timedelta(days=1), time(10, 15)),   # morning
    (LEAD_B, today + timedelta(days=1), time(14, 45)),   # afternoon
    (LEAD_A, today + timedelta(days=2), time(19, 30)),   # evening
]

print(f"Seeding {len(seed_rows)} rows into dev call_schedules...")
for lead_id, sched_date, sched_time in seed_rows:
    dt = datetime.combine(sched_date, sched_time)  # naive, exactly like the UI
    payload = {
        "lead_id": lead_id,
        "scheduled_by": "[SEED] Test Counselor",
        "scheduled_time": dt.isoformat(),
        "status": "Pending",
    }
    res = client.table("call_schedules").insert(payload).execute()
    row = res.data[0]
    print(f"  inserted id={row['id']}  scheduled_time={row['scheduled_time']}  (naive local intent: {dt.isoformat()})")

print("Done.")
