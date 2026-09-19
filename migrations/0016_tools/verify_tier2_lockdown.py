"""
Post-apply verification for migration 0016 (Tier 2 lockdown). DEV (or a
loopback scratch DB) gets everything; prod runs only the read-only checks:

    python migrations/0016_tools/verify_tier2_lockdown.py --env dev
    python migrations/0016_tools/verify_tier2_lockdown.py --env prod --read-only-only

Checks (PASS/FAIL with the raw facts; exit status non-zero on any FAIL):
  1. Tier 2: anon AND authenticated hold NO table privilege.
  2. Tier 2: service_role keeps SELECT/INSERT/UPDATE/DELETE (dce_crm's new key).
  3. Tier 2: RLS enabled, and no literal-true policy remains (allow_all gone).
  4. Tier 1 REGRESSION: anon AND authenticated still have no privilege (0015 intact).
  5. Behaviour, read-only: SET ROLE anon / authenticated -> SELECT count(*) on each
     Tier 2 table must fail with 42501; SET ROLE service_role -> must succeed.
     (SKIPPED, not failed, if this DB user is not allowed to SET ROLE.)
  6. Default privileges (skipped with --read-only-only): a throw-away table created in
     public inside a transaction that is ALWAYS rolled back gets no anon/authenticated grants.
"""
import argparse
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "0015_tools"))
from _common import TABLE_PRIVS, TIER1_TABLES, TIER2_TABLES, connect, q, show  # noqa: E402

results = []


def record(name, ok, detail=""):
    results.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))


def priv_list(cur, role, table):
    return [p for p in TABLE_PRIVS if q(cur, "SELECT has_table_privilege(%s, %s, %s)", (role, f"public.{table}", p))[0][0]]


def check_privileges(cur):
    print("\n=== 1/2. privileges on Tier 2 ===")
    for t in TIER2_TABLES:
        for role in ("anon", "authenticated"):
            g = priv_list(cur, role, t)
            record(f"{t}: {role} has no privileges", not g, f"still granted: {g}" if g else "none")
        miss = [p for p in ("SELECT", "INSERT", "UPDATE", "DELETE")
                if not q(cur, "SELECT has_table_privilege('service_role', %s, %s)", (f"public.{t}", p))[0][0]]
        record(f"{t}: service_role keeps SELECT/INSERT/UPDATE/DELETE", not miss, f"missing: {miss}" if miss else "all four")


def check_rls_policies(cur):
    print("\n=== 3. RLS + policies on Tier 2 ===")
    for t in TIER2_TABLES:
        rls = q(cur, "SELECT relrowsecurity FROM pg_class WHERE oid=%s::regclass", (f"public.{t}",))[0][0]
        record(f"{t}: RLS enabled", bool(rls))
    rows = q(cur, """SELECT tablename, policyname FROM pg_policies WHERE schemaname='public'
                     AND tablename = ANY(%s) AND (qual='true' OR with_check='true')""", (TIER2_TABLES,))
    record("no literal-true policy remains on Tier 2", not rows, f"remaining: {rows}" if rows else "0 found")
    show(cur, "policies still present on Tier 2 (expected: none)",
         "SELECT tablename, policyname, cmd, roles, qual, with_check FROM pg_policies WHERE schemaname='public' AND tablename = ANY(%s) ORDER BY 1,2",
         (TIER2_TABLES,))


def check_tier1_regression(cur):
    print("\n=== 4. Tier 1 must STILL be locked (0015 intact) ===")
    for t in TIER1_TABLES:
        bad = {r: priv_list(cur, r, t) for r in ("anon", "authenticated")}
        bad = {r: p for r, p in bad.items() if p}
        record(f"{t}: anon+authenticated still have no privileges", not bad, f"granted: {bad}" if bad else "none")


def check_behaviour(env, local_url):
    print("\n=== 5. behaviour: SET ROLE + SELECT count(*) (read-only) ===")
    conn = connect(env, local_url, readonly=True)  # autocommit: an error does not poison the session
    cur = conn.cursor()
    for role, must_succeed in (("anon", False), ("authenticated", False), ("service_role", True)):
        try:
            cur.execute(f"SET ROLE {role}")
        except Exception as e:
            print(f"SKIP  cannot SET ROLE {role}: {str(e).strip().splitlines()[0]}")
            continue
        for t in TIER2_TABLES:
            try:
                cur.execute(f'SELECT count(*) FROM public."{t}"')
                n = cur.fetchone()[0]
                record(f"as {role}: SELECT count(*) FROM {t} {'works' if must_succeed else 'is refused'}", must_succeed, f"count={n}" if must_succeed else f"UNEXPECTEDLY returned count={n}")
            except Exception as e:
                code = getattr(e, "pgcode", None)
                ok = (not must_succeed) and code == "42501"
                record(f"as {role}: SELECT count(*) FROM {t} {'works' if must_succeed else 'is refused'}", ok, f"pgcode={code}")
        cur.execute("RESET ROLE")
    conn.close()


def check_default_privileges(env, local_url):
    print("\n=== 6. default privileges (rolled-back throw-away table) ===")
    conn = connect(env, local_url, readonly=False)
    cur = conn.cursor()
    name = f"_probe_0016_{uuid.uuid4().hex[:8]}"
    try:
        cur.execute(f"CREATE TABLE public.{name} (id int)")
        got = {r: [p for p in TABLE_PRIVS if q(cur, "SELECT has_table_privilege(%s, %s, %s)", (r, f"public.{name}", p))[0][0]] for r in ("anon", "authenticated")}
        record("new table in public gets no anon/authenticated grants", not any(got.values()), f"anon={got['anon']} authenticated={got['authenticated']}")
        cur.execute(f"DROP TABLE public.{name}")
    except Exception as e:
        record("default-privileges probe ran", False, f"{type(e).__name__}: {str(e).strip().splitlines()[0]}")
    finally:
        conn.rollback()
        cur.execute("SELECT to_regclass(%s) IS NULL", (f"public.{name}",))
        print(f"probe table gone after rollback: {cur.fetchone()[0]}")
        conn.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", choices=["dev", "prod"], required=True)
    ap.add_argument("--read-only-only", action="store_true", help="skip the rolled-back default-privileges test (required for prod)")
    ap.add_argument("--local-url")
    args = ap.parse_args()
    if args.env == "prod" and not args.read_only_only:
        sys.exit("Refusing: --env prod requires --read-only-only (no test writes on prod).")
    print(f"##### 0016 VERIFY - ENV = {args.env.upper()}{' (read-only checks only)' if args.read_only_only else ''} #####")
    conn = connect(args.env, args.local_url, readonly=True)
    cur = conn.cursor()
    print("connected as:", q(cur, "SELECT current_user")[0][0])
    check_privileges(cur)
    check_rls_policies(cur)
    check_tier1_regression(cur)
    conn.close()
    check_behaviour(args.env, args.local_url)
    if not args.read_only_only:
        check_default_privileges(args.env, args.local_url)
    failed = [n for n, ok in results if not ok]
    print(f"\n##### {len(results) - len(failed)}/{len(results)} checks passed #####")
    if failed:
        print("FAILED:")
        for n in failed:
            print("  -", n)
        sys.exit(1)


if __name__ == "__main__":
    main()
