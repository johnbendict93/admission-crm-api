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
    python migrations/run_migrations.py verify --env dev
    python migrations/run_migrations.py backfill-checksums --env dev

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

CHECKSUM / DRIFT DETECTION
---------------------------
Every migration file is hashed (SHA-256) at the moment it's applied or
stamped, and that hash is stored alongside the applied record in
`schema_migrations`. This exists because of a real incident: migration
0001 was recorded as applied on the assumption that dev already matched
the dumped schema, when it actually didn't (dev was missing a trigger
0001 couldn't capture) — and nothing in the tool noticed until tests
started failing for an unrelated reason. A stored hash means "applied"
now means something checkable, not just an assertion.

`status` shows a CHECKSUM column (ok / MISMATCH / none) for a quick look.
`verify` does the strict version: it re-hashes every migration file on
disk that's marked applied, compares it against the stored hash, and
exits non-zero — printing exactly which file(s) changed — if anything
doesn't match. Run it any time you want to confirm nothing already-applied
has been edited since (worth adding to a routine local check; CI never
holds prod credentials so it can't run this against prod).

`backfill-checksums` computes and stores a hash for any applied migration
that predates this feature (i.e. has no stored checksum yet — the three
migrations applied on dev/prod before this was added). It captures
whatever is on disk *right now* as the trusted baseline going forward —
it cannot retroactively prove that baseline is what was actually run
originally, only that nothing changes after the backfill without being
caught. Run it once per environment right after this feature ships.
"""
import argparse
import hashlib
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

# Applied before checksum tracking existed; added separately (rather than
# just in CREATE_TRACKING_TABLE above) so it also lands on tables created
# by an older copy of this script, via IF NOT EXISTS.
ADD_CHECKSUM_COLUMN = """
ALTER TABLE public.schema_migrations ADD COLUMN IF NOT EXISTS checksum text;
"""


def file_checksum(path: Path) -> str:
    """SHA-256 of the migration file's content, with CRLF normalized to LF
    first. Content-based, not path-based, so renaming a file without
    touching its contents does not register as drift.

    The normalization isn't theoretical: it was hit live (Sept 2026) when
    restoring a deliberately-tampered migration file via `git checkout --`
    on Windows silently reintroduced CRLF endings (Windows Git's autocrlf
    conversion), changing the file's raw bytes with no change to its SQL
    content - and a raw-byte hash flagged that as drift. A .gitattributes
    entry (`*.sql text eol=lf`) now pins these files to LF on checkout for
    every contributor regardless of local core.autocrlf, but normalizing
    here too is a second, independent safeguard - a tool or editor that
    resaves a file outside of git wouldn't be caught by .gitattributes
    alone.
    """
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


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


def get_applied(cur) -> dict[str, dict]:
    """Returns {version: {"applied_at": str, "checksum": str | None}}."""
    cur.execute(CREATE_TRACKING_TABLE)
    cur.execute(ADD_CHECKSUM_COLUMN)
    cur.execute("SELECT version, applied_at, checksum FROM public.schema_migrations ORDER BY version;")
    return {row[0]: {"applied_at": str(row[1]), "checksum": row[2]} for row in cur.fetchall()}


def cmd_status(args, conn) -> None:
    with conn.cursor() as cur:
        applied = get_applied(cur)
    conn.commit()
    migrations = discover_migrations()
    if not migrations:
        print("No migration files found.")
        return
    print(f"{'VERSION':<8} {'STATUS':<10} {'CHECKSUM':<10} {'APPLIED AT':<26} DESCRIPTION")
    for version, description, path in migrations:
        if version in applied:
            stored = applied[version]["checksum"]
            if stored is None:
                checksum_status = "none"
            elif stored == file_checksum(path):
                checksum_status = "ok"
            else:
                checksum_status = "MISMATCH"
            print(f"{version:<8} {'applied':<10} {checksum_status:<10} {applied[version]['applied_at']:<26} {description}")
        else:
            print(f"{version:<8} {'PENDING':<10} {'':<10} {'':<26} {description}")


def cmd_verify(args, conn) -> None:
    """Strict drift check: re-hash every applied migration's file on disk
    and compare against the hash stored at apply/stamp time. Exits non-zero
    if anything marked applied no longer matches what's on disk, and prints
    exactly which file(s) changed. A migration with no stored checksum
    (applied before this feature existed) is reported separately and does
    NOT fail the check — run `backfill-checksums` to give it a baseline."""
    with conn.cursor() as cur:
        applied = get_applied(cur)
    conn.commit()

    migrations = discover_migrations()
    mismatches: list[str] = []
    unchecked: list[str] = []

    for version, description, path in migrations:
        if version not in applied:
            continue
        stored = applied[version]["checksum"]
        if stored is None:
            unchecked.append(f"  {version}  {description}  ({path.name})")
            continue
        current = file_checksum(path)
        if current != stored:
            mismatches.append(
                f"  {version}  {description}  ({path.name})\n"
                f"      stored checksum:  {stored}\n"
                f"      on-disk checksum: {current}"
            )

    if unchecked:
        print("No stored checksum (applied before drift detection existed — run backfill-checksums):")
        print("\n".join(unchecked))
        print()

    if mismatches:
        print(f"DRIFT DETECTED — {len(mismatches)} applied migration file(s) changed after being applied to {args.env}:")
        print("\n".join(mismatches))
        sys.exit(1)

    print(f"OK — every checksummed migration applied to {args.env} matches its file on disk.")


def cmd_backfill_checksums(args, conn) -> None:
    """One-time (per environment) baseline: store a checksum for every
    already-applied migration that doesn't have one yet. This trusts
    whatever is on disk right now — it cannot prove that's what was
    originally run, only that nothing changes after this point without
    being caught by `verify`."""
    with conn.cursor() as cur:
        applied = get_applied(cur)
    conn.commit()

    migrations = {v: p for v, _d, p in discover_migrations()}
    if args.force:
        # Recompute even migrations that already have a stored checksum.
        # Needed once, right now, because file_checksum()'s algorithm just
        # changed (raw bytes -> CRLF-normalized) and because 0001/prod's
        # line endings were just cleaned up via .gitattributes - both mean
        # the previously-stored checksums no longer reflect a meaningful
        # baseline. Also the right tool if the hashing algorithm ever
        # changes again, instead of resetting checksum to NULL by hand.
        to_backfill = [v for v in applied if v in migrations]
    else:
        to_backfill = [v for v in applied if applied[v]["checksum"] is None and v in migrations]

    if not to_backfill:
        print(f"Nothing to backfill — every applied migration on {args.env} already has a stored checksum.")
        return

    verb = "recompute (--force)" if args.force else "backfill"
    print(f"About to {verb} checksums for {len(to_backfill)} migration(s) on {args.env}, using the file currently on disk as the trusted baseline:")
    for version in to_backfill:
        print(f"  {version}  ({migrations[version].name})")

    if args.env == "prod" and not args.yes:
        confirm = input(
            "\nType 'BACKFILL PRODUCTION' to continue: "
        )
        if confirm != "BACKFILL PRODUCTION":
            sys.exit("Aborted — confirmation phrase did not match.")

    with conn.cursor() as cur:
        for version in to_backfill:
            checksum = file_checksum(migrations[version])
            cur.execute(
                "UPDATE public.schema_migrations SET checksum = %s WHERE version = %s;",
                (checksum, version),
            )
    conn.commit()
    print(f"Backfilled {len(to_backfill)} checksum(s) on {args.env}.")


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
        checksum = file_checksum(path)
        print(f"Applying {version} ({description})...")
        with conn.cursor() as cur:
            cur.execute(sql)
            cur.execute(
                "INSERT INTO public.schema_migrations (version, description, checksum) VALUES (%s, %s, %s);",
                (version, description, checksum),
            )
        conn.commit()
        print(f"  done.")
    print(f"Applied {len(pending)} migration(s) to {args.env}.")


def cmd_stamp(args, conn) -> None:
    migrations = {v: (d, p) for v, d, p in discover_migrations()}
    if args.version not in migrations:
        sys.exit(f"No migration file found for version {args.version}.")
    description, path = migrations[args.version]

    with conn.cursor() as cur:
        applied = get_applied(cur)
        if args.version in applied:
            conn.commit()
            sys.exit(f"{args.version} is already recorded as applied (at {applied[args.version]['applied_at']}).")

        if args.env == "prod" and not args.yes:
            confirm = input(
                f"\nYou are about to STAMP migration {args.version} as applied to "
                "PRODUCTION without running its SQL.\n"
                "Type 'STAMP PRODUCTION' to continue: "
            )
            if confirm != "STAMP PRODUCTION":
                sys.exit("Aborted — confirmation phrase did not match.")

        checksum = file_checksum(path)
        cur.execute(
            "INSERT INTO public.schema_migrations (version, description, checksum) VALUES (%s, %s, %s);",
            (args.version, description, checksum),
        )
    conn.commit()
    print(f"Stamped {args.version} ({description}) as applied to {args.env}, without running its SQL.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    for name, fn in (("status", cmd_status), ("apply", cmd_apply), ("verify", cmd_verify)):
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

    p_backfill = sub.add_parser(
        "backfill-checksums",
        help="Store a checksum for already-applied migrations that predate drift detection.",
    )
    p_backfill.add_argument("--env", choices=["dev", "prod"], required=True, help="No default — must be explicit.")
    p_backfill.add_argument("--yes", action="store_true", help="Skip the interactive prod confirmation prompt.")
    p_backfill.add_argument("--force", action="store_true", help="Recompute checksums that are already set, not just missing ones.")
    p_backfill.set_defaults(func=cmd_backfill_checksums)

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
