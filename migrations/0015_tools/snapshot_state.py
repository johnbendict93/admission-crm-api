"""
Snapshot the LIVE grants / RLS state / policies / default privileges of the
Tier 1 tables and write a ROLLBACK script that restores exactly that state.
Run this BEFORE applying migration 0015, once per environment:

    python migrations/0015_tools/snapshot_state.py --env dev
    python migrations/0015_tools/snapshot_state.py --env prod     (before prod)

Read-only: the session is opened readonly=True and only SELECTs run. Output:
    migrations/rollback/0015_rollback_<env>.sql

The generated script is idempotent (drops-then-recreates every policy, sets
RLS/FORCE back to the recorded value, re-grants the recorded privileges) and
wrapped in a transaction. Nothing secret is written - only role names, table
names and policy expressions.

STATE_FINGERPRINT (printed, and stored in the file) is a SHA-256 of the
state body, so "state before apply" and "state after rollback" can be
compared for exact equality.
"""
import argparse
import hashlib
import sys
from datetime import datetime, timezone

from _common import REPO_ROOT, TIER1_TABLES, TIER2_TABLES, connect, q

ROLES = ("anon", "authenticated")


def qi(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def collect(cur):
    state = {"tables": {}, "grants": [], "policies": [], "default_acl": [], "tier2": {}}

    cur.execute(
        """
        SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity, c.relowner::regrole::text
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind IN ('r','p') AND c.relname = ANY(%s)
        ORDER BY c.relname
        """,
        (TIER1_TABLES,),
    )
    for name, rls, force, owner in cur.fetchall():
        state["tables"][name] = {"rls": rls, "force": force, "owner": owner}
    missing = [t for t in TIER1_TABLES if t not in state["tables"]]
    if missing:
        sys.exit(f"Tier 1 table(s) missing in this database: {missing}. Refusing to write a partial rollback.")

    cur.execute(
        """
        SELECT c.relname, r.rolname, a.privilege_type, a.is_grantable
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        CROSS JOIN LATERAL aclexplode(c.relacl) a
        JOIN pg_roles r ON r.oid = a.grantee
        WHERE n.nspname = 'public' AND c.relname = ANY(%s) AND r.rolname = ANY(%s)
        ORDER BY c.relname, r.rolname, a.privilege_type
        """,
        (TIER1_TABLES, list(ROLES)),
    )
    state["grants"] = cur.fetchall()

    cur.execute(
        """
        SELECT tablename, policyname, permissive, cmd, roles, qual, with_check
        FROM pg_policies WHERE schemaname = 'public' AND tablename = ANY(%s)
        ORDER BY tablename, policyname
        """,
        (TIER1_TABLES,),
    )
    state["policies"] = cur.fetchall()

    cur.execute(
        """
        SELECT d.defaclrole::regrole::text,
               CASE WHEN d.defaclnamespace = 0 THEN '(all schemas)' ELSE d.defaclnamespace::regnamespace::text END,
               d.defaclobjtype::text, r.rolname, a.privilege_type, a.is_grantable
        FROM pg_default_acl d
        CROSS JOIN LATERAL aclexplode(d.defaclacl) a
        JOIN pg_roles r ON r.oid = a.grantee
        ORDER BY 1, 2, 3, 4, 5
        """
    )
    state["default_acl"] = cur.fetchall()

    # Tier 2 is recorded for reference only (never restored/modified here).
    cur.execute(
        """
        SELECT c.relname, c.relrowsecurity,
               (SELECT count(*) FROM pg_policies p WHERE p.schemaname='public' AND p.tablename=c.relname)
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relname = ANY(%s) ORDER BY 1
        """,
        (TIER2_TABLES,),
    )
    state["tier2"] = {r[0]: {"rls": r[1], "policies": r[2]} for r in cur.fetchall()}
    return state


def grant_sql(rows):
    """rows: (table, grantee, privilege, grantable) -> GRANT statements, one
    per (table, grantee, grantable) so WITH GRANT OPTION is preserved."""
    grouped = {}
    for table, grantee, priv, grantable in rows:
        grouped.setdefault((table, grantee, grantable), []).append(priv)
    out = []
    for (table, grantee, grantable), privs in sorted(grouped.items()):
        out.append(
            f"GRANT {', '.join(sorted(privs))} ON TABLE public.{qi(table)} TO {qi(grantee)}"
            + (" WITH GRANT OPTION;" if grantable else ";")
        )
    return out


def policy_sql(row):
    table, name, permissive, cmd, roles, qual, with_check = row
    role_list = ", ".join(("PUBLIC" if r == "public" else qi(r)) for r in roles) if roles else "PUBLIC"
    parts = [
        f"CREATE POLICY {qi(name)} ON public.{qi(table)} AS {permissive} FOR {cmd} TO {role_list}"
    ]
    if qual is not None:
        parts.append(f"USING ({qual})")
    if with_check is not None:
        parts.append(f"WITH CHECK ({with_check})")
    return " ".join(parts) + ";"


def build_body(state):
    lines = []
    for t in TIER1_TABLES:
        meta = state["tables"][t]
        lines.append(f"-- {t}: owner={meta['owner']} rls={meta['rls']} force_rls={meta['force']}")
    lines.append("")
    lines.append("-- Policies: drop every policy recorded (so re-creation cannot collide), then re-create.")
    for row in state["policies"]:
        lines.append(f"DROP POLICY IF EXISTS {qi(row[1])} ON public.{qi(row[0])};")
    for row in state["policies"]:
        lines.append(policy_sql(row))
    lines.append("")
    lines.append("-- RLS / FORCE RLS exactly as recorded.")
    for t in TIER1_TABLES:
        meta = state["tables"][t]
        lines.append(f"ALTER TABLE public.{qi(t)} {'ENABLE' if meta['rls'] else 'DISABLE'} ROW LEVEL SECURITY;")
        lines.append(f"ALTER TABLE public.{qi(t)} {'FORCE' if meta['force'] else 'NO FORCE'} ROW LEVEL SECURITY;")
    lines.append("")
    lines.append("-- Grants to anon / authenticated exactly as recorded (REVOKE first so the result is exact).")
    for t in TIER1_TABLES:
        lines.append(f"REVOKE ALL ON TABLE public.{qi(t)} FROM anon, authenticated;")
    lines.extend(grant_sql(state["grants"]))
    lines.append("")
    lines.append("-- Default privileges in schema public for anon/authenticated (0015 revoked these for the migration role).")
    dacl = [r for r in state["default_acl"] if r[1] == "public" and r[2] == "r" and r[3] in ROLES]
    grouped = {}
    for role, _schema, _objtype, grantee, priv, grantable in dacl:
        grouped.setdefault((role, grantee, grantable), []).append(priv)
    if not grouped:
        lines.append("-- (none were present at snapshot time)")
    for (role, grantee, grantable), privs in sorted(grouped.items()):
        lines.append(
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {qi(role)} IN SCHEMA public "
            f"GRANT {', '.join(sorted(privs))} ON TABLES TO {qi(grantee)}"
            + (" WITH GRANT OPTION;" if grantable else ";")
        )
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", choices=["dev", "prod"], required=True)
    ap.add_argument("--out", help="output path (default migrations/rollback/0015_rollback_<env>.sql)")
    ap.add_argument("--local-url", help="loopback-only URL, for testing this tool against a scratch Postgres")
    args = ap.parse_args()

    conn = connect(args.env, args.local_url, readonly=True)
    cur = conn.cursor()
    cur.execute("SELECT current_user, now()")
    who, now = cur.fetchone()
    state = collect(cur)
    body = build_body(state)
    fingerprint = hashlib.sha256(body.encode()).hexdigest()

    out = REPO_ROOT / (args.out or f"migrations/rollback/0015_rollback_{args.env}.sql")
    out.parent.mkdir(parents=True, exist_ok=True)
    header = (
        f"-- ROLLBACK for migration 0015 - restores the {args.env.upper()} state captured by\n"
        f"-- migrations/0015_tools/snapshot_state.py at {datetime.now(timezone.utc).isoformat(timespec='seconds')} "
        f"(connected as {who}).\n"
        f"-- Generated from the LIVE database BEFORE 0015 was applied. Apply with the SAME environment only:\n"
        f"--     psql / any client on the {args.env.upper()} DATABASE_URL, run this file as one transaction.\n"
        f"-- STATE_FINGERPRINT={fingerprint}\n\n"
    )
    sql = header + "BEGIN;\n\n" + body + "\nCOMMIT;\n"
    out.write_text(sql, encoding="utf-8", newline="\n")

    print(f"##### 0015 SNAPSHOT - ENV = {args.env.upper()} (read-only) #####")
    print(f"connected as: {who}")
    shown = out.relative_to(REPO_ROOT) if REPO_ROOT in out.parents else out
    print(f"written: {shown}  ({len(sql.splitlines())} lines)")
    print(f"STATE_FINGERPRINT={fingerprint}")
    print("\n--- Tier 1 tables (rls / force / owner)")
    for t in TIER1_TABLES:
        m = state["tables"][t]
        print(f"{t} | rls={m['rls']} | force={m['force']} | owner={m['owner']}")
    print(f"\n--- recorded grants to anon/authenticated on Tier 1: {len(state['grants'])} privilege rows")
    print(f"--- recorded policies on Tier 1: {len(state['policies'])}")
    for r in state["policies"]:
        print(f"{r[0]} | {r[1]} | {r[3]} | roles={r[4]} | using={'true' if r[5]=='true' else ('(expr)' if r[5] else 'NULL')} | check={'true' if r[6]=='true' else ('(expr)' if r[6] else 'NULL')}")
    print("\n--- ALL default privilege entries in this database (role | schema | objtype | grantee | privilege)")
    for r in state["default_acl"]:
        print(" | ".join(str(x) for x in r[:5]))
    print("\n--- Tier 2 (NOT touched by 0015; recorded for reference)")
    for t in TIER2_TABLES:
        print(f"{t} | {state['tier2'].get(t)}")
    conn.close()


if __name__ == "__main__":
    main()
