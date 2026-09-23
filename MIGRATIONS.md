# Migrations

Schema changes go through numbered SQL files in `migrations/`, applied in
order and tracked in a `schema_migrations` table. This is deliberately a
thin, standardized tool rather than an ORM migration framework, per the
project's Golden Rule.

Why a separate tool at all: the app talks to Supabase only through
PostgREST (`supabase-py`), which can do CRUD but not DDL. `CREATE TABLE`,
`ALTER TABLE`, `CREATE POLICY`, etc. require a direct Postgres connection.
`migrations/run_migrations.py` is the one thing in this repo that opens
that direct connection — everything else keeps using `SUPABASE_URL`/
`SUPABASE_KEY` as before.

## One-time setup

Add a direct Postgres connection string for each environment to `.env`
(Supabase dashboard → Connect → Connection string → URI). These are
separate from `SUPABASE_URL`/`SUPABASE_KEY` and are used only by the
migration runner:

```
DEV_DATABASE_URL=postgresql://postgres:<password>@<dev-host>:5432/postgres
PROD_DATABASE_URL=postgresql://postgres:<password>@<prod-host>:5432/postgres
```

Install the one added dependency (`psycopg2-binary`) if you haven't
already:

```
pip install -r requirements.txt
```

## Writing a new migration

1. Create the next numbered file: `migrations/000N_short_description.sql`
   (four-digit, zero-padded, sequential — e.g. `0002_add_soft_deletes.sql`).
2. Write plain SQL. Prefer idempotent forms where practical
   (`CREATE TABLE IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS`, etc.) so a
   migration is safe to re-read even though it will only ever actually
   *run* once per database (the runner records it in `schema_migrations`
   the moment it succeeds and skips it on every later run).
3. Do not hand-edit the schema in the Supabase SQL Editor. If it isn't in
   a numbered migration file, it isn't tracked, and dev/prod will drift.

## Checking status

```
python migrations/run_migrations.py status --env dev
python migrations/run_migrations.py status --env prod
```

Lists every migration file and whether it's applied (with timestamp) or
pending, for that specific environment. There is no default `--env` —
every invocation must say which database it's asking about.

## Applying to dev

```
python migrations/run_migrations.py apply --env dev
```

Runs every pending migration, in order, inside a transaction per file,
and records each one in `schema_migrations` as it succeeds.

## Applying to prod

Deliberately, never automatically — this repo's CI never even holds
production credentials, so it is structurally incapable of doing this for
you.

```
python migrations/run_migrations.py apply --env prod
```

This prompts for a typed confirmation phrase (`APPLY TO PRODUCTION`)
before touching anything. Run this yourself, by hand, after the same
migration has already been applied to dev and verified there.

## Migration 0001 is special: stamped, not applied

`0001_initial_schema.sql` is a retroactive capture of the schema that was
already live in both dev and prod *before* this migrations system
existed (captured via `pg_dump --schema-only` against production, then
restored into dev — see `migrations/prod_schema.sql` for the original
untouched dump). Both databases already have this schema. Running it with
`apply` would fail with "already exists" errors — instead, record it as
applied without executing it:

```
python migrations/run_migrations.py stamp --env dev  --version 0001
python migrations/run_migrations.py stamp --env prod --version 0001
```

`stamp` also prompts for confirmation on `--env prod`. Every migration
after 0001 is a genuinely new, not-yet-applied change and goes through
`apply` normally, on dev first and then, once verified, on prod.

## Migration 0015: Tier 1 anon/authenticated lockdown

Revokes every privilege from `anon` and `authenticated` on the twelve tables
only the API touches (the API uses service_role), enables RLS on them, drops
their literal-`true` policies, and stops future tables in `public` from
auto-granting to those roles. The five tables `dce_crm` still reads with the
anon key (`leads, followups, call_schedules, campus_visits, telecallers`) are
deliberately NOT touched - they are locked down later, after `dce_crm` has
been moved to a server-side service key. Tooling lives in
`migrations/0015_tools/`; the migration header explains the reasoning.

Run order, **dev first, prod only after the dev output has been reviewed**
(each step is read-only unless it says APPLY):

```
python check_0015_preflight.py --env dev                       # facts: function owner, follow_ups, runner role
python migrations/0015_tools/anon_probe.py --env dev --write-probe   # BEFORE: anon can read/write everything
python migrations/0015_tools/snapshot_state.py --env dev       # writes migrations/rollback/0015_rollback_dev.sql
python migrations/run_migrations.py apply --env dev            # APPLY (dev)
python migrations/0015_tools/verify_lockdown.py --env dev      # 61 checks; includes two rolled-back write tests
python migrations/0015_tools/anon_probe.py --env dev --write-probe   # AFTER: Tier 1 denied, Tier 2 still open
pytest                                                         # full suite (216)
```

Prod (by hand, with the typed confirmation): take a **prod** snapshot first
(`snapshot_state.py --env prod` - never reuse dev's rollback file, the two
states differ: prod has RLS off on five of these tables), run the read-only
`anon_probe.py --env prod`, then `run_migrations.py apply --env prod`, then
`verify_lockdown.py --env prod --read-only-only` and the prod probe again.
To roll back, run the matching `migrations/rollback/0015_rollback_<env>.sql`
against that environment as one transaction, then delete the `0015` row from
`schema_migrations` so the migration shows as pending again.

Side effect on prod: `dce_crm/verify_live_deployed_app.py` and
`verify_soft_delete_visibility_fix.py` read `users` with the anon key and will
stop working (they are one-off scripts, not app code).


## Migration 0016 (APPLIED dev 2026-09-19, prod 2026-09-20): Tier 2 anon/authenticated lockdown

**Status: APPLIED.** Dev: 2026-09-19 17:03:29 UTC. Prod: 2026-09-20 07:20:51 UTC (0017 one
second later). The file is `migrations/0016_lock_down_tier2_anon_access.sql` (released from
`migrations/pending/` by commit `db97a37`).

It revokes ALL from `anon` and `authenticated` on `leads`, `followups`,
`call_schedules`, `campus_visits`, `telecallers`, enables RLS and drops the `allow_all`
(true/true) policies. It had to wait until every dce_crm consumer ran on a server-side
`service_role` key - with the anon key dce_crm stops working the moment this lands.

**Applied record**

- Rollback files (generated from the LIVE db BEFORE apply, both committed):
  `migrations/rollback/0016_rollback_dev.sql` (commit `db97a37`) and
  `migrations/rollback/0016_rollback_prod.sql` (commit `846cc92`). Both carry
  `STATE_FINGERPRINT=bc797b0f46bd3ed12f81b155c1cb65ed793ef083769d5f3f24ac8ec35351db4e`
  (dev and prod Tier 2 started in the identical state). To roll back, run the matching
  file for the SAME environment as one transaction (Supabase SQL editor), then delete the
  0016 row from `schema_migrations`.
- Dev: `verify_tier2_lockdown.py --env dev` 49/49; `anon_probe.py --env dev --write-probe`
  all 17 tables denied (12 x 401/42501, 5 x 500/42P17 which is the harmless `users`
  policy recursion), row counts unchanged.
- Prod: `verify_tier2_lockdown.py --env prod --read-only-only` 48/48; `anon_probe.py --env prod`
  same 17-table pattern; service_role row counts unchanged (leads 5, followups 1,
  call_schedules 1, campus_visits 0, telecallers 0).
- dce_crm on both stages behaved the same: five Tier 2 pages load, writes save (incl. an
  offset-aware call_schedules write stored as the correct UTC instant), and the daily report
  sends with live counts. Prod's Streamlit Cloud `SUPABASE_KEY` was swapped to the prod
  `service_role` JWT before 0016 and the live app kept working after it.
- `scheduler.py` is NOT running for prod (the prod sender's Sent folder has only the Sep 4
  test reports). If it is ever started it must use the `service_role` key too.
- Still on the anon key (will fail against the locked tables until swapped): the local
  prod copy's `.streamlit/secrets.toml`, and the untracked `verify_*.py` one-off scripts in
  dce_crm. The API itself uses the anon key only for `sign_in_with_password` (auth, unaffected).

Tooling in `migrations/0016_tools/` (reuses `migrations/0015_tools/_common.py`):

```
python migrations/0016_tools/snapshot_tier2.py --env dev     # BEFORE apply -> migrations/rollback/0016_rollback_dev.sql
python migrations/0016_tools/verify_tier2_lockdown.py --env dev                      # after apply (dev: incl. rolled-back default-privileges test)
python migrations/0016_tools/verify_tier2_lockdown.py --env prod --read-only-only    # prod: read-only checks
python migrations/0015_tools/anon_probe.py --env <env>       # after: every table denied
python migrations/0016_tools/rpc_probe.py --env dev          # DEV ONLY: can anon call the 4 trigger functions via /rpc ?
```

Planned order: dev copy of dce_crm on the dev anon key (baseline) -> dev secret key
(same behaviour) -> dev snapshot + apply 0016 -> verify + probe -> prod key swap in
Streamlit Cloud and the scheduler -> confirm dce_crm works on prod -> prod snapshot
+ apply.

### Migration 0017 (APPLIED dev 2026-09-19, prod 2026-09-20; no-op on prod): revoke anon EXECUTE on `rls_auto_enable()`

`rpc_probe.py` on dev: the four trigger functions are NOT exposed over REST (404 /
PGRST202) so they need nothing; `public.rls_auto_enable()` (event trigger,
SECURITY DEFINER, present on dev only) IS reachable (400 / 0A000 - it is invoked, then
refuses). `migrations/0017_revoke_anon_execute_rls_auto_enable.sql` revokes
EXECUTE from PUBLIC/anon/authenticated, guarded so it is a no-op where the function does
not exist. Independent of 0016 (no dce_crm dependency). Check owner/ACL first
(`check_tier2_audit.py`, section 6).

### dce_crm dev rehearsal (done before 0016): `migrations/0016_tools/setup_dce_crm_dev.ps1`

Builds `..\dce_crm_dev` (a remote-less clone of dce_crm) with a dev-only
`.streamlit\secrets.toml`: dev URL + key from this repo's `.env` (never printed),
Groq/SMTP credentials dummied (or your own dev sender with `-EnableEmail`), report
recipient forced to `-Recipient`. `-Stage 1` = dev anon key (baseline), `-Stage 2` = dev
secret key (the rehearsal for prod's service_role swap). It aborts unless the secrets path is
git-ignored, and checks `git status` is clean afterwards. It never modifies the prod copy.

Order (do not reorder): dev config -> dev baseline (Stage 1) -> dev key swap (Stage 2) ->
dev 0016 -> prod key swap + daily-report scheduler -> prod verify -> prod 0016.

Test plan, run by hand in the dev app once per stage (both stages must behave the same):
leads, followups, call schedules, campus visits and telecallers pages all load; one real
write in each area you use (call_schedules matters most: offset-aware datetime from 0014);
"Send Daily Report Now" to your own address arrives (needs `-EnableEmail`); the report's AI
summary reads "AI Error: ..." because the Groq key is a dummy - that is expected.
supabase-py must be >= 2.17 for `sb_secret_` / `sb_publishable_` keys (2.15 rejects them);
prod's legacy service_role JWT works on any version.

### Migrations 0019 + 0020: applied to PROD 2026-09-23

Both were dev-only until now (fee_due_schedule, enquiry_monthly_history -
brand-new empty tables, nothing existing references them). Found when a
read-only prod inventory returned APIError for both tables. Applied with
`python migrations/run_migrations.py apply --env prod` (confirmation phrase
typed by John): "Applied 2 migration(s) to prod." Rollbacks:
`migrations/rollback/0019_rollback_prod.sql`, `0020_rollback_prod.sql`.
