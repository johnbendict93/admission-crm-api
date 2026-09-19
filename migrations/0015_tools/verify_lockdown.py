"""
Post-apply verification for migration 0015. DEV (or a loopback scratch DB)
only - it refuses --env prod because two of its checks do (always rolled-
back) test writes. Prod is verified with the read-only anon_probe.py plus
--read-only-only on this script:

    python migrations/0015_tools/verify_lockdown.py --env dev
    python migrations/0015_tools/verify_lockdown.py --env prod --read-only-only

Checks (each prints PASS/FAIL with the raw facts behind it):
  1. Tier 1: anon and authenticated hold NO table privilege at all.
  2. Tier 1: service_role still has SELECT/INSERT/UPDATE/DELETE (the API's key).
  3. Tier 1: RLS is enabled on every table.
  4. Tier 1: no policy with a literal `true` USING / WITH CHECK remains.
  5. Tier 2: UNTOUCHED - anon still has all four DML privileges and the
     allow_all policy is still present (proves the scope of 0015).
  6. Default privileges: a throw-away table created in public (inside a
     transaction that is ALWAYS rolled back) gets no anon/authenticated grants.
  7. Auth trigger + RLS: inserting a throw-away auth.users row (rolled back)
     still produces its public.users row through handle_new_auth_user().
Checks 6 and 7 are skipped with --read-only-only.
Exit status is non-zero if any check FAILS or COULD NOT BE CHECKED.
"""
import argparse
import sys
import uuid

from _common import TABLE_PRIVS, TIER1_TABLES, TIER2_TABLES, connect, q, show

results = []


def record(name, ok, detail=""):
    results.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))


def check_privileges(cur):
    print("\n=== 1/2. privileges on Tier 1 ===")
    for t in TIER1_TABLES:
        for role in ("anon", "authenticated"):
            granted = [p for p in TABLE_PRIVS if q(cur, "SELECT has_table_privilege(%s, %s, %s)", (role, f"public.{t}", p))[0][0]]
            record(f"{t}: {role} has no privileges", not granted, f"still granted: {granted}" if granted else "none")
        missing = [p for p in ("SELECT", "INSERT", "UPDATE", "DELETE") if not q(cur, "SELECT has_table_privilege('service_role', %s, %s)", (f"public.{t}", p))[0][0]]
        record(f"{t}: service_role keeps SELECT/INSERT/UPDATE/DELETE", not missing, f"missing: {missing}" if missing else "all four")


def check_rls_and_policies(cur):
    print("\n=== 3/4. RLS + policies on Tier 1 ===")
    for t in TIER1_TABLES:
        rls = q(cur, "SELECT relrowsecurity FROM pg_class WHERE oid = %s::regclass", (f"public.{t}",))[0][0]
        record(f"{t}: RLS enabled", bool(rls))
    rows = q(
        cur,
        """SELECT tablename, policyname, cmd, qual, with_check FROM pg_policies
           WHERE schemaname='public' AND tablename = ANY(%s) AND (qual = 'true' OR with_check = 'true')""",
        (TIER1_TABLES,),
    )
    record("no literal-true policy remains on Tier 1", not rows, f"remaining: {[(r[0], r[1]) for r in rows]}" if rows else "0 found")
    show(cur, "policies still present on Tier 1 (all should be predicate-based)",
         "SELECT tablename, policyname, cmd, roles, qual, with_check FROM pg_policies WHERE schemaname='public' AND tablename = ANY(%s) ORDER BY 1,2",
         (TIER1_TABLES,))


def check_tier2_untouched(cur):
    print("\n=== 5. Tier 2 must be UNTOUCHED ===")
    for t in TIER2_TABLES:
        dml = [p for p in ("SELECT", "INSERT", "UPDATE", "DELETE") if q(cur, "SELECT has_table_privilege('anon', %s, %s)", (f"public.{t}", p))[0][0]]
        pol = q(cur, "SELECT count(*) FROM pg_policies WHERE schemaname='public' AND tablename=%s AND qual='true' AND with_check='true'", (t,))[0][0]
        record(f"{t}: anon still has SELECT/INSERT/UPDATE/DELETE", len(dml) == 4, f"has: {dml}")
        record(f"{t}: allow_all (true/true) policy still present", pol >= 1, f"{pol} found")


def check_default_privileges(env, local_url):
    print("\n=== 6. default privileges (rolled-back throw-away table) ===")
    conn = connect(env, local_url, readonly=False)
    cur = conn.cursor()
    name = f"_probe_0015_{uuid.uuid4().hex[:8]}"
    try:
        cur.execute(f"CREATE TABLE public.{name} (id int)")
        granted = {}
        for role in ("anon", "authenticated"):
            granted[role] = [p for p in TABLE_PRIVS if q(cur, "SELECT has_table_privilege(%s, %s, %s)", (role, f"public.{name}", p))[0][0]]
        record("new table in public gets no anon/authenticated grants", not any(granted.values()), f"anon={granted['anon']} authenticated={granted['authenticated']}")
    except Exception as e:
        record("default-privileges probe ran", False, f"{type(e).__name__}: {str(e).strip().splitlines()[0]}")
    finally:
        conn.rollback()
        cur.execute("SELECT to_regclass(%s) IS NULL", (f"public.{name}",))
        print(f"probe table rolled back (no longer exists): {cur.fetchone()[0]}")
        conn.close()


def check_auth_trigger(env, local_url):
    print("\n=== 7. auth trigger still works with RLS on public.users (rolled-back test insert) ===")
    conn = connect(env, local_url, readonly=False)
    cur = conn.cursor()
    uid = str(uuid.uuid4())
    email = f"rls-probe-{uid[:8]}@pytest.invalid"
    try:
        cur.execute("SELECT current_user")
        print("running as:", cur.fetchone()[0])
        cur.execute("INSERT INTO auth.users (id, email) VALUES (%s, %s)", (uid, email))
        cur.execute("SELECT id, role, is_active FROM public.users WHERE id = %s", (uid,))
        row = cur.fetchone()
        record("auth.users insert provisions a public.users row via the trigger", row is not None, f"row={row}")
    except Exception as e:
        record("auth trigger probe ran", False, f"{type(e).__name__}: {str(e).strip().splitlines()[0]}")
    finally:
        conn.rollback()
        cur.execute("SELECT count(*) FROM auth.users WHERE id = %s", (uid,))
        a = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM public.users WHERE id = %s", (uid,))
        p = cur.fetchone()[0]
        print(f"after rollback: auth.users rows={a}, public.users rows={p} (both must be 0)")
        conn.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", choices=["dev", "prod"], required=True)
    ap.add_argument("--read-only-only", action="store_true", help="skip the two rolled-back write checks (required for prod)")
    ap.add_argument("--local-url")
    args = ap.parse_args()
    if args.env == "prod" and not args.read_only_only:
        sys.exit("Refusing: --env prod requires --read-only-only (no test writes on prod).")

    print(f"##### 0015 VERIFY - ENV = {args.env.upper()}{' (read-only checks only)' if args.read_only_only else ''} #####")
    conn = connect(args.env, args.local_url, readonly=True)
    cur = conn.cursor()
    print("connected as:", q(cur, "SELECT current_user")[0][0])
    check_privileges(cur)
    check_rls_and_policies(cur)
    check_tier2_untouched(cur)
    conn.close()
    if not args.read_only_only:
        check_default_privileges(args.env, args.local_url)
        check_auth_trigger(args.env, args.local_url)

    failed = [n for n, ok in results if not ok]
    print(f"\n##### {len(results) - len(failed)}/{len(results)} checks passed #####")
    if failed:
        print("FAILED:")
        for n in failed:
            print("  -", n)
        sys.exit(1)


if __name__ == "__main__":
    main()
