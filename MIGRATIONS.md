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
