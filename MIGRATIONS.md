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


## Migration 0016 (DRAFT, NOT APPLIED): Tier 2 anon/authenticated lockdown

**Status: draft. Not applied to dev or prod.** The file is
`migrations/pending/0016_lock_down_tier2_anon_access.sql` - deliberately outside
`migrations/*.sql`, which is all `run_migrations.py` discovers, so no `apply` run can
pick it up by accident. To release it, `git mv` it into `migrations/` in the same change
that applies it.

It revokes ALL from `anon` and `authenticated` on `leads`, `followups`,
`call_schedules`, `campus_visits`, `telecallers`, enables RLS and drops the `allow_all`
(true/true) policies. **Do not apply until dce_crm (the Streamlit Cloud app, `scheduler.py`,
and any other consumer) runs on a server-side `service_role` key** - with the anon key it
stops working the moment this lands.

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
+ apply. A `REVOKE EXECUTE` on the trigger functions is separate and only written if
`rpc_probe.py` shows they are reachable.
