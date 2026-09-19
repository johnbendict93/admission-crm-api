"""
DEV ONLY. Can the anon key call the public trigger functions through
PostgREST's /rest/v1/rpc/<fn> ? Prints STATUS + error code only - never a body,
never the key. Decides whether a separate REVOKE EXECUTE migration is needed.

    python migrations/0016_tools/rpc_probe.py --env dev

Function list comes from the database (read-only): every public function
that anon may EXECUTE. Each is POSTed once with an empty JSON body. A trigger
function cannot run outside a trigger (Postgres raises 0A000), and PostgREST
does not expose trigger-returning functions at all (404 / PGRST202), so this is
side-effect free; it is nevertheless refused on prod.
Interpretation:
    404 + PGRST202          not exposed over REST      -> no REVOKE needed
    401/403 + 42501         denied                     -> no REVOKE needed
    400/500 + 0A000 (or any error that proves the function was INVOKED)
                            reachable -> write a REVOKE EXECUTE migration
    200/204                 function ran -> reachable, definitely REVOKE
"""
import argparse
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "0015_tools"))
from _common import connect, q  # noqa: E402
from anon_probe import classify_key, err_code, headers_for  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", choices=["dev", "prod"], required=True)
    ap.add_argument("--local-url")
    ap.add_argument("--test-base-url")
    args = ap.parse_args()
    if args.env != "dev":
        sys.exit("Refusing: rpc_probe is DEV ONLY.")

    if args.test_base_url:  # tool self-test against a loopback mock only
        import os
        base, key = args.test_base_url.rstrip("/"), os.environ["ANON_PROBE_TEST_KEY"]
    else:
        from app.core.config import settings

        base, key = settings.DEV_SUPABASE_URL.rstrip("/"), settings.DEV_SUPABASE_ANON_KEY
    kind, role = classify_key(key)
    print("##### RPC PROBE - ENV = DEV #####")
    print(f"key kind: {kind} | role: {role} | length: {len(key)}  (key itself never printed)")
    if kind == "secret" or role != "anon":
        sys.exit("Refusing: not an anon key.")

    conn = connect("dev", args.local_url, readonly=True)
    cur = conn.cursor()
    fns = q(cur, """SELECT p.proname, pg_get_function_result(p.oid), p.prosecdef
                    FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
                    WHERE n.nspname='public' AND has_function_privilege('anon', p.oid, 'EXECUTE') ORDER BY 1""")
    conn.close()
    client = httpx.Client(timeout=30)
    print("\nfunction | returns | security_definer | POST /rest/v1/rpc/<fn> status | error code")
    for name, returns, secdef in fns:
        r = client.post(f"{base}/rest/v1/rpc/{name}", json={}, headers=headers_for(key, kind, {"Content-Type": "application/json"}))
        print(f"{name} | {returns} | {secdef} | {r.status_code} | {err_code(r)}")
    print("\nRead the table above with the interpretation in this script's docstring.")


if __name__ == "__main__":
    main()
