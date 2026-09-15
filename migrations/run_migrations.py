#!/usr/bin/env python3
"""
Lightweight, numbered-SQL-file migration runner for the Admission CRM API.

Per the project's Golden Rule ("don't reach for a heavy ORM-migration
framework unless there's a clear reason to"), this is deliberately simple:
plain numbered .sql files in this directory, applied in order, tracked in
a `schema_migrations` table so re-runs are idempotent and auditable.

Why a separate script instead of the app's normal Supabase client:
DDL (CREATE TABLE / ALTER TABLE / CREATE POLICY / etc.) cannot go through
PostgREST (the REST API `supabase-py` talks to) — it requires a direct
Postgres connection. That connection string (DEV_DATABASE_URL /
PROD_DATABASE_URL) is a completely different credential from
SUPABASE_URL/SUPABASE_KEY, which the app uses at runtime for ordinary
CRUD. This script is the only thing in the codebase that needs it.

Commands:
    python migrations/run_migrations.py status --env dev
    python migrations/run_migrations.py apply  --env dev
    python migrations/run_migrations.py apply  --env prod
    python migrations/run_migrations.py stamp  --env dev  --version 0001

There is deliberately NO default --env — every invocation must say which
database it is touching. `apply --env prod` additionally requires typing
a confirmation phrase at an interactive prompt (or --yes to skip it, which
should be reserved for a deliberate, attended one-off, never routine or
automated use — this project's CI intentionally never has prod credentials
at all, so it can never call this script against prod).

`stamp` records a migration as applied WITHOUT running its SQL. This
exists for exactly one situation: migration 0001, which retroactively
captures a schema that was already live in both dev and prod before this
tool existed (see the header comment in 0001_initial_schema.sql).
"""
import argparse
import re
import sys
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent
VERSION_RE = re.compile(r"^(\d{4})_(.+)\.sql$")

CREATE_TRACKING_TABLE = """
CREATE TABLE IF NOT EXISTS public.schema_migrations (
    version     text PRIMARY KEY,
    description text NOT NULL,
    applied_at  timestamptz NOT NULL DEFAULT now()
);
"""


def get_database_url(env: str) -> str:
    # Imported lazily so `--help` works without the app's dependencies
    # (and without a fully populated .env) being available.
    sys.path.insert(0, str(MIGRATIONS_DIR.parent))
    from app.core.config import settings  # noqa: E402

    url = settings.DEV_DATABASE_URL if env == "dev" else settings.PROD_DATABASE_URL
    field = "DEV_DATABASE_URL" if env == "dev" else "PROD_DATABASE_URL"
    if not url:
        sys.exit(
            f"{field} is not set in .env. This must be a direct Postgres "
            "connection string (Supabase dashboard → Connect → "
            "Connection string → URI), not the SUPABASE_URL/SUPABASE_KEY "
            "used by the app itself."
        )
    return url


def discover_migrations() -> list[tuple[str, str, Path]]:
    """Return every migrations/NNNN_description.sql file as
    (version, description, path), sorted by version. Raises on a
    duplicate version number rather than silently picking one."""
    found: dict[str, Path] = {}
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        m = VERSION_RE.match(path.name)
        if not m:
            continue
        version, description = m.group(1), m.group(2)
        if version in found:
            sys.exit(f"Duplicate migration version {version}: {found[version].name} and {path.name}")
        found[version] = path
    return [(v, found[v].stem.split("_", 1)[1].replace("_", " "), found[v]) for v in sorted(found)]


def get_applied(cur) -> dict[str, str]:
    cur.execute(CREATE_TRACKING_TABLE)
    cur.execute("SELECT version, applied_at FROM public.schema_migrations ORDER BY version;")
    return {row[0]: str(row[1]) for row in cur.fetchall()}


def cmd_status(args, conn) -> None:
    with conn.cursor() as cur:
        applied = get_applied(cur)
    conn.commit()
    migrations = discover_migrations()
    if not migrations:
        print("No migration files found.")
        return
    print(f"{'VERSION':<8} {'STATUS':<10} {'APPLIED AT':<26} DESCRIPTION")
    for version, description, _path in migrations:
        if version in applied:
            print(f"{version:<8} {'applied':<10} {applied[version]:<26} {description}")
        else:
            print(f"{version:<8} {'PENDING':<10} {'':<26} {description}")


def cmd_apply(args, conn) -> None:
    with conn.cursor() as cur:
        applied = get_applied(cur)
    conn.commit()

    pending = [m for m in discover_migrations() if m[0] not in applied]
    if not pending:
        print("Nothing to apply — already up to date.")
        return

    print(f"Pending migrations for {args.env}:")
    for version, description, _path in pending:
        print(f"  {version}  {description}")

    if args.env == "prod" and not args.yes:
        confirm = input(
            "\nYou are about to apply the above migration(s) to PRODUCTION.\n"
            "Type 'APPLY TO PRODUCTION' to continue: "
        )
        if confirm != "APPLY TO PRODUCTION":
            sys.exit("Aborted — confirmation phrase did not match.")

    for version, description, path in pending:
        sql = path.read_text()
        print(f"Applying {version} ({description})...")
        with conn.cursor() as cur:
            cur.execute(sql)
            cur.execute(
                "INSERT INTO public.schema_migrations (version, description) VALUES (%s, %s);",
                (version, description),
            )
        conn.commit()
        print(f"  done.")
    print(f"Applied {len(pending)} migration(s) to {args.env}.")


def cmd_stamp(args, conn) -> None:
    migrations = {v: (d, p) for v, d, p in discover_migrations()}
    if args.version not in migrations:
        sys.exit(f"No migration file found for version {args.version}.")
    description, _path = migrations[args.version]

    with conn.cursor() as cur:
        applied = get_applied(cur)
        if args.version in applied:
            conn.commit()
            sys.exit(f"{args.version} is already recorded as applied (at {applied[args.version]}).")

        if args.env == "prod" and not args.yes:
            confirm = input(
                f"\nYou are about to STAMP migration {args.version} as applied to "
                "PRODUCTION without running its SQL.\n"
                "Type 'STAMP PRODUCTION' to continue: "
            )
            if confirm != "STAMP PRODUCTION":
                sys.exit("Aborted — confirmation phrase did not match.")

        cur.execute(
            "INSERT INTO public.schema_migrations (version, description) VALUES (%s, %s);",
            (args.version, description),
        )
    conn.commit()
    print(f"Stamped {args.version} ({description}) as applied to {args.env}, without running its SQL.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    for name, fn in (("status", cmd_status), ("apply", cmd_apply)):
        p = sub.add_parser(name)
        p.add_argument("--env", choices=["dev", "prod"], required=True, help="No default — must be explicit.")
        if name == "apply":
            p.add_argument("--yes", action="store_true", help="Skip the interactive prod confirmation prompt.")
        p.set_defaults(func=fn)

    p_stamp = sub.add_parser("stamp", help="Record a migration as applied without running its SQL.")
    p_stamp.add_argument("--env", choices=["dev", "prod"], required=True, help="No default — must be explicit.")
    p_stamp.add_argument("--version", required=True, help="e.g. 0001")
    p_stamp.add_argument("--yes", action="store_true", help="Skip the interactive prod confirmation prompt.")
    p_stamp.set_defaults(func=cmd_stamp)

    args = parser.parse_args()

    try:
        import psycopg2
    except ImportError:
        sys.exit("psycopg2 is not installed. Run: pip install -r requirements.txt")

    database_url = get_database_url(args.env)
    conn = psycopg2.connect(database_url)
    try:
        args.func(args, conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
