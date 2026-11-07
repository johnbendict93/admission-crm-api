# Timezone inconsistency — audit findings and proposal (not yet executed)

Scope: the 6 legacy naive-`timestamp` columns across the 5 tables you flagged —
`leads.created_at`, `telecallers.created_at`, `call_schedules.created_at`,
`call_schedules.scheduled_time`, `campus_visits.created_at`,
`followups.created_at`. Nothing below has been applied. No schema was
touched, no migration file was created, no app code was changed. This is
the audit + plan you asked for before touching anything.

## Important limitation on how this was verified

I could not run live queries against dev myself this session — the shell I
use on your machine only has network access to a small allowlist (npm/PyPI/
GitHub-type hosts), and it can't reach Supabase's Postgres endpoint or even
plain HTTPS to supabase.com (I confirmed this directly: DNS resolution and a
generic HTTPS request to supabase.com both failed at the proxy). That's a
different constraint than "credentials" — it's a network boundary. So the
schema and code findings below are grounded in the actual repo/schema files
(prod_schema.sql, the app's routers/services, and the Streamlit source), but
two specific claims still need a live confirmation from you, in your own
terminal, before we act on them. Both are single, read-only queries — see
"Before doing anything" below.

## What the schema actually has

From `migrations/prod_schema.sql`:

| Table | Column | Type | Set by |
|---|---|---|---|
| leads | created_at | `timestamp without time zone` DEFAULT now() | DB default only |
| telecallers | created_at | `timestamp without time zone` DEFAULT now() | DB default only |
| call_schedules | created_at | `timestamp without time zone` DEFAULT now() | DB default only |
| call_schedules | scheduled_time | `timestamp without time zone` | **the app** (Streamlit and the API both write it) |
| campus_visits | created_at | `timestamp without time zone` DEFAULT now() | DB default only |
| campus_visits | visit_date | `date` | app — not a timestamp, no tz ambiguity, out of scope |
| followups | created_at | `timestamp without time zone` DEFAULT now() | DB default only |
| followups | call_date / call_time | `date` / `text` | app — neither is a real timestamp column, out of scope |

Useful context: every `deleted_at` column added later, across all 14
tables (migrations 0003–0012), was typed `timestamptz` from the start. So
this isn't a fresh design mistake — it's legacy debt confined to columns
that predate this API project, inherited from the original Streamlit-only
schema. Everything built since has already been doing this correctly.

## What actually reads/writes these columns

**The `created_at` columns** (5 of the 6) are never written by application
code anywhere — in the API repo or in `dce_crm` — they're 100% `DEFAULT
now()`. Nobody sets them explicitly. That makes them the simple case: their
value is whatever Postgres's `now()` produced under the session's timezone
at insert time, consistently, every time.

**`call_schedules.scheduled_time` is different — it's the one column
actually written by application code, and both sides write it the same
(uninstrumented) way:**

- `dce_crm/pages/6_Scheduling_Visits_Telecallers.py` (lines ~19-41):
  ```python
  sched_date = st.date_input("Call Date *", value=date.today())
  sched_time = st.time_input("Call Time *")
  ...
  dt = datetime.combine(sched_date, sched_time)
  insert_schedule({..., "scheduled_time": dt.isoformat(), ...})
  ```
  `datetime.combine()` produces a naive `datetime` — no tzinfo attached at
  all. `.isoformat()` on a naive datetime emits a string with **no UTC
  offset** (e.g. `2026-09-18T14:30:00`). Whatever wall-clock time the
  counselor typed into the picker is what gets sent, verbatim, with no
  timezone marker.
- The API's own `CallScheduleCreate`/`CallScheduleUpdate` models
  (`app/models/call_schedules.py`) type `scheduled_time` as a plain
  `Optional[datetime]`, and the API's own test suite
  (`tests/test_call_schedules.py`) sends it the same way: a bare
  `"2026-10-01T10:30:00"` string, no offset.

So today, both writers agree with each other, but neither writer commits to
a timezone — they just pass along "whatever the local wall clock said."
Given DCE is in Chennai, that's almost certainly meant to be IST
(Asia/Kolkata, UTC+5:30) — but nothing in the code says so explicitly, and
nothing converts it.

## The actual finding: this is two different problems, not one migration

**Case A — the five `DEFAULT now()` columns.** If (and only if) the
Postgres session that evaluates `now()` runs in UTC — which is Supabase's
documented default for managed projects — then these naive values already
*are* UTC clock time, just missing the label. Converting `timestamp` →
`timestamptz` for a column like this, **run under a UTC session**, is
provably safe and cheap: PostgreSQL added an optimization in version 12
specifically for this case. Per the Postgres developer discussion I checked
(Bruce Momjian, on the pgsql-hackers list): `timestamp` and `timestamptz`
are binary-identical on disk when the session timezone is UTC, so the
conversion is a catalog-only change — no row-by-row rewrite, no scan of the
table, and the `ACCESS EXCLUSIVE` lock (which this DDL always requires,
regardless of rewrite) is held only for the instant it takes to update the
catalog, not for a bulk rewrite. That's a materially different risk profile
than "locks the table while every row gets rewritten," which is the
generic (non-UTC) case people usually mean when they warn about this
migration.

**Case B — `call_schedules.scheduled_time`.** This one is not
binary-safe, because its stored values are not UTC — they're naive local
(IST) wall-clock time written directly by the app, as shown above. If you
ran the exact same `ALTER COLUMN ... TYPE timestamptz` on this column,
PostgreSQL would apply the *same* UTC-session assumption to existing rows —
silently reinterpreting every already-scheduled call time as if it had been
UTC all along, shifting every one of them by 5.5 hours. That's a real data
bug, not just a lock/performance cost, and it does require a genuine
rewrite (`... USING scheduled_time AT TIME ZONE 'Asia/Kolkata'`, converting
the local values to true UTC as part of the type change) rather than the
cheap reinterpretation available in Case A.

There's a second half to Case B that a schema change alone doesn't fix:
even after the column is `timestamptz`, both writers (Streamlit's
`dt.isoformat()` and the API's own request payloads) are still sending
naive, offset-less strings. PostgREST/Postgres will interpret those
according to *its own* session timezone at write time — if that's UTC (the
same assumption as everywhere else), a naive `"14:30:00"` meant as 2:30pm
IST would be stored as 2:30pm UTC (8:00pm IST) — wrong, in the opposite
direction. So converting this column's type without also updating both
writers to send a real offset (or convert to UTC before sending) would
trade one silent bug for another. This is the part of the plan that needs
an actual code change, not just a migration.

## Before doing anything: two things to confirm yourself

I can't run these from here (see the network limitation above). Both are
read-only, dev-only, and safe:

1. Confirm the session timezone Case A's safety argument depends on:
   ```sql
   SHOW timezone;
   ```
   Expected: `UTC`. If it's anything else, Case A's "no rewrite" claim
   does not hold and the whole plan needs rethinking.

2. Confirm `scheduled_time` really is naive local time and not something
   already-converted:
   ```sql
   SELECT id, scheduled_time, created_at FROM call_schedules
   ORDER BY created_at DESC LIMIT 5;
   ```
   Sanity-check a couple of these against what you'd expect a counselor to
   have actually typed for that call (roughly business hours in IST).

If you can run those two and paste back the output, that closes the last
gap between "this is what the code says should happen" and "this is
verified against live dev data."

## Recommended phased plan (draft only — not created as a migration file)

**Phase 1 — Case A, the five `DEFAULT now()` columns.** Once `SHOW
timezone` confirms UTC, a single additive migration, same style as your
existing numbered files:

```sql
-- 0013_convert_legacy_created_at_to_timestamptz.sql (draft, not created)
ALTER TABLE public.leads           ALTER COLUMN created_at TYPE timestamptz;
ALTER TABLE public.telecallers     ALTER COLUMN created_at TYPE timestamptz;
ALTER TABLE public.call_schedules  ALTER COLUMN created_at TYPE timestamptz;
ALTER TABLE public.campus_visits   ALTER COLUMN created_at TYPE timestamptz;
ALTER TABLE public.followups       ALTER COLUMN created_at TYPE timestamptz;
```
No `USING` clause needed for this one (that's what keeps it a
reinterpretation instead of a rewrite). No app-code change needed either:
PostgREST will start emitting these with an explicit `+00:00` suffix
instead of a bare string, which every existing consumer (Streamlit's raw
`st.dataframe` display, the API's `Optional[datetime]` Pydantic fields)
already handles fine — it's strictly less ambiguous than today, not a
breaking wire-format change.

**Phase 2 — Case B, `scheduled_time` — separate, more careful migration
plus a small code change:**
```sql
-- draft only
ALTER TABLE public.call_schedules
  ALTER COLUMN scheduled_time TYPE timestamptz
  USING scheduled_time AT TIME ZONE 'Asia/Kolkata';
```
This one *does* rewrite the table (small table, so cheap in practice, but
worth doing in a maintenance window rather than assuming it's free like
Phase 1). Paired with it: update `dce_crm`'s `insert_schedule`/
`update_schedule` call site and the API's `call_schedules` create/update
path so both attach the IST offset explicitly before sending (e.g.
`dt.replace(tzinfo=ZoneInfo("Asia/Kolkata")).isoformat()` on the Streamlit
side), so newly-written rows after the migration are correct going in, not
just correctly reinterpreted going forward.

**Verification before either phase touches prod:** run Phase 1 on dev
first, then confirm empirically (not just by citation) that no rewrite
happened — compare the table's `pg_class.relfilenode` before and after
(unchanged = no rewrite), and check `pg_stat_activity`/lock wait time
during the ALTER. That test needs to run somewhere with real network
access to dev — either your own terminal, or tell me and I'll write the
exact script for you to run and paste back, the same pattern we've used
for pytest and migrations throughout this project.

## What I'm explicitly not proposing

I'm not proposing to touch `campus_visits.visit_date`, `followups.call_date`,
or `followups.call_time` — none of those are timestamp types, so the
`timestamp`-vs-`timestamptz` question doesn't apply to them. (`call_time`
being stored as free-text `text` rather than a `time` type is arguably its
own small smell, but it's a different issue than the one you asked about,
so I've left it out of scope here.)
