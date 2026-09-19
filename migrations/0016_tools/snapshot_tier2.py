"""
Snapshot the LIVE grants / RLS state / policies of the five Tier 2 tables and
write a ROLLBACK script that restores exactly that state. Run BEFORE applying
migration 0016, once per environment:

    python migrations/0016_tools/snapshot_tier2.py --env dev
    python migrations/0016_tools/snapshot_tier2.py --env prod     (before prod)

Read-only (session opened readonly=True, SELECTs only). Output:
    migrations/rollback/0016_rollback_<env>.sql
Same approach as 0015's snapshot_state.py (whose statement builders it
reuses); STATE_FINGERPRINT lets "before apply" and "after rollback" be
compared for exact equality. Nothing secret is written.
"""
import argparse
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "0015_tools"))
from _common import REPO_ROOT, TIER1_TABLES, TIER2_TABLES, connect  # noqa: E402
from snapshot_state import ROLES, grant_sql, policy_sql, qi  # noqa: E402


def collect(cur):
    st = {"tables": {}, "grants": [], "policies": [], "tier1_locked": {}}
    cur.execute(
        """SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity, c.relowner::regrole::text
           FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
           WHERE n.nspname='public' AND c.relkind IN ('r','p') AND c.relname = ANY(%s) ORDER BY 1""",
        (TIER2_TABLES,),
    )
    for name, rls, force, owner in cur.fetchall():
        st["tables"][name] = {"rls": rls, "force": force, "owner": owner}
    missing = [t for t in TIER2_TABLES if t not in st["tables"]]
    if missing:
        sys.exit(f"Tier 2 table(s) missing in this database: {missing}. Refusing to write a partial rollback.")
    cur.execute(
        """SELECT c.relname, r.rolname, a.privilege_type, a.is_grantable
           FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
           CROSS JOIN LATERAL aclexplode(c.relacl) a JOIN pg_roles r ON r.oid=a.grantee
           WHERE n.nspname='public' AND c.relname = ANY(%s) AND r.rolname = ANY(%s)
           ORDER BY 1,2,3""",
        (TIER2_TABLES, list(ROLES)),
    )
    st["grants"] = cur.fetchall()
    cur.execute(
        """SELECT tablename, policyname, permissive, cmd, roles, qual, with_check
           FROM pg_policies WHERE schemaname='public' AND tablename = ANY(%s) ORDER BY 1,2""",
        (TIER2_TABLES,),
    )
    st["policies"] = cur.fetchall()
    # reference only: 0015 must still hold (never modified by this tool / 0016)
    for t in TIER1_TABLES:
        cur.execute(
            "SELECT has_table_privilege('anon', %s, 'SELECT,INSERT,UPDATE,DELETE'), has_table_privilege('authenticated', %s, 'SELECT,INSERT,UPDATE,DELETE')",
            (f"public.{t}", f"public.{t}"),
        )
        st["tier1_locked"][t] = not any(cur.fetchone())
    return st


def build_body(st):
    lines = []
    for t in TIER2_TABLES:
        m = st["tables"][t]
        lines.append(f"-- {t}: owner={m['owner']} rls={m['rls']} force_rls={m['force']}")
    lines += ["", "-- Policies: drop every recorded policy (so re-creation cannot collide), then re-create."]
    lines += [f"DROP POLICY IF EXISTS {qi(r[1])} ON public.{qi(r[0])};" for r in st["policies"]]
    lines += [policy_sql(r) for r in st["policies"]]
    lines += ["", "-- RLS / FORCE RLS exactly as recorded."]
    for t in TIER2_TABLES:
        m = st["tables"][t]
        lines.append(f"ALTER TABLE public.{qi(t)} {'ENABLE' if m['rls'] else 'DISABLE'} ROW LEVEL SECURITY;")
        lines.append(f"ALTER TABLE public.{qi(t)} {'FORCE' if m['force'] else 'NO FORCE'} ROW LEVEL SECURITY;")
    lines += ["", "-- Grants to anon / authenticated exactly as recorded (REVOKE first so the result is exact)."]
    lines += [f"REVOKE ALL ON TABLE public.{qi(t)} FROM anon, authenticated;" for t in TIER2_TABLES]
    lines += grant_sql(st["grants"])
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", choices=["dev", "prod"], required=True)
    ap.add_argument("--out")
    ap.add_argument("--local-url", help="loopback-only URL (tool self-test against a scratch Postgres)")
    args = ap.parse_args()

    conn = connect(args.env, args.local_url, readonly=True)
    cur = conn.cursor()
    cur.execute("SELECT current_user")
    who = cur.fetchone()[0]
    st = collect(cur)
    body = build_body(st)
    fp = hashlib.sha256(body.encode()).hexdigest()
    out = REPO_ROOT / (args.out or f"migrations/rollback/0016_rollback_{args.env}.sql")
    out.parent.mkdir(parents=True, exist_ok=True)
    header = (
        f"-- ROLLBACK for migration 0016 - restores the {args.env.upper()} state captured by\n"
        f"-- migrations/0016_tools/snapshot_tier2.py at {datetime.now(timezone.utc).isoformat(timespec='seconds')} (connected as {who}).\n"
        f"-- Generated from the LIVE database BEFORE 0016 was applied (0016 is a DRAFT until then).\n"
        f"-- Apply to the SAME environment only, as one transaction. Then delete the 0016 row from schema_migrations.\n"
        f"-- STATE_FINGERPRINT={fp}\n\n"
    )
    sql = header + "BEGIN;\n\n" + body + "\nCOMMIT;\n"
    out.write_text(sql, encoding="utf-8", newline="\n")

    print(f"##### 0016 SNAPSHOT - ENV = {args.env.upper()} (read-only) #####")
    print(f"connected as: {who}")
    print(f"written: {out.relative_to(REPO_ROOT) if REPO_ROOT in out.parents else out}  ({len(sql.splitlines())} lines)")
    print(f"STATE_FINGERPRINT={fp}")
    print("\n--- Tier 2 tables (rls / force / owner)")
    for t in TIER2_TABLES:
        m = st["tables"][t]
        print(f"{t} | rls={m['rls']} | force={m['force']} | owner={m['owner']}")
    print(f"\n--- recorded grants to anon/authenticated on Tier 2: {len(st['grants'])} privilege rows")
    print(f"--- recorded policies on Tier 2: {len(st['policies'])}")
    for r in st["policies"]:
        print(f"{r[0]} | {r[1]} | {r[3]} | roles={r[4]} | using={'true' if r[5]=='true' else ('(expr)' if r[5] else 'NULL')} | check={'true' if r[6]=='true' else ('(expr)' if r[6] else 'NULL')}")
    print("\n--- reference: Tier 1 still locked for anon+authenticated (0015 intact)?")
    for t in TIER1_TABLES:
        print(f"{t} | locked={st['tier1_locked'][t]}")
    conn.close()


if __name__ == "__main__":
    main()
