"""
Anon-key exposure probe: what can the PUBLIC anon key actually do to each
public table through the REST API? Prints status codes and counts ONLY -
never row data, never the key.

    python migrations/0015_tools/anon_probe.py --env dev --write-probe
    python migrations/0015_tools/anon_probe.py --env prod                (read-only)

For every public table (listed from the DB over a READ-ONLY direct
connection):
  * GET  /rest/v1/<table>?select=*&limit=0  with `Prefer: count=exact`
        -> status + exact row count (the count is what anon can see)
  * DEV ONLY, with --write-probe: PATCH /rest/v1/<table>?<pk>=eq.<impossible>
        setting one column to null. The filter matches ZERO rows by
        construction and this is double-checked over the direct connection
        before each PATCH (count must be 0 or that table's PATCH is skipped),
        so no data can change. 200/204 = the write was ACCEPTED (anon has the
        privilege and RLS let it through); 401/403 (Postgres 42501) = DENIED.
        Limitation: with RLS on and no permitting policy, an UPDATE that
        matches nothing also returns 200/204, so on such a table "accepted"
        proves only that the privilege exists, not that rows are writable.
  * Total row counts of every table are compared before/after all probes.

Key handling: the anon key is read locally - dev: DEV_SUPABASE_ANON_KEY from
.env; prod: dce_crm's .streamlit/secrets.toml (the key dce_crm really ships
with; cross-checked against PROD_SUPABASE_ANON_KEY as a boolean only). The
script REFUSES to run with anything that is not an anon/publishable key
(service_role / sb_secret_ are rejected), and never prints it.
"""
import argparse
import base64
import json
import os
import re
import sys
from pathlib import Path

import httpx

from _common import REPO_ROOT, _is_loopback, connect, q

IMPOSSIBLE = {
    "uuid": "00000000-0000-0000-0000-000000000000",
    "text": "__anon_probe_no_such_row__",
    "varchar": "__anon_probe_no_such_row__",
    "int2": -999999999,
    "int4": -999999999,
    "int8": -999999999,
}


def classify_key(key: str):
    """-> (kind, role). kind: 'jwt' | 'publishable' | 'secret' | 'unknown'."""
    if key.startswith("sb_publishable_"):
        return "publishable", "anon"
    if key.startswith("sb_secret_"):
        return "secret", "service_role"
    if key.count(".") == 2:
        try:
            p = key.split(".")[1]
            p += "=" * (-len(p) % 4)
            return "jwt", json.loads(base64.urlsafe_b64decode(p)).get("role")
        except Exception:
            return "jwt", None
    return "unknown", None


def read_secrets_toml_key(path: Path):
    text = path.read_text(encoding="utf-8")
    key = re.search(r'^\s*SUPABASE_KEY\s*=\s*"([^"]+)"', text, re.M)
    url = re.search(r'^\s*SUPABASE_URL\s*=\s*"([^"]+)"', text, re.M)
    if not key or not url:
        sys.exit(f"Could not find SUPABASE_URL / SUPABASE_KEY in {path}")
    return key.group(1), url.group(1).rstrip("/")


def headers_for(key: str, kind: str, extra=None):
    h = {"apikey": key}
    if kind == "jwt":  # new-style sb_publishable_ keys must NOT be sent as a Bearer token
        h["Authorization"] = f"Bearer {key}"
    h.update(extra or {})
    return h


def count_from(resp):
    cr = resp.headers.get("content-range", "")
    return cr.split("/")[-1] if "/" in cr else "?"


def err_code(resp):
    try:
        body = resp.json()
        return body.get("code") or ""
    except Exception:
        return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", choices=["dev", "prod"], required=True)
    ap.add_argument("--write-probe", action="store_true", help="DEV ONLY: impossible-filter PATCH per table")
    ap.add_argument("--secrets", help="path to dce_crm secrets.toml (prod key source)")
    ap.add_argument("--local-url", help="loopback DB url (tool self-test only)")
    ap.add_argument("--test-base-url", help="loopback REST base url (tool self-test only)")
    args = ap.parse_args()

    if args.write_probe and args.env != "dev":
        sys.exit("Refusing: --write-probe is DEV ONLY. Prod gets read-count probes, never writes.")

    from app.core.config import settings  # noqa: E402

    if args.test_base_url:
        if not _is_loopback(args.test_base_url.replace("http://", "postgresql://x@")):
            sys.exit("--test-base-url must be loopback")
        base, key, source = args.test_base_url.rstrip("/"), os.environ["ANON_PROBE_TEST_KEY"], "TEST-KEY (self-test)"
    elif args.env == "dev":
        base, key, source = settings.DEV_SUPABASE_URL.rstrip("/"), settings.DEV_SUPABASE_ANON_KEY, "API .env DEV_SUPABASE_ANON_KEY"
    else:
        secrets = Path(args.secrets) if args.secrets else (REPO_ROOT.parent / "dce_crm" / ".streamlit" / "secrets.toml")
        key, secrets_url = read_secrets_toml_key(secrets)
        base, source = secrets_url, f"dce_crm secrets.toml ({secrets.name})"
        print(f"dce_crm key == PROD_SUPABASE_ANON_KEY in .env: {key == settings.PROD_SUPABASE_ANON_KEY}")
        print(f"dce_crm URL == PROD_SUPABASE_URL in .env: {secrets_url == settings.PROD_SUPABASE_URL.rstrip('/')}")

    kind, role = classify_key(key)
    print(f"##### ANON PROBE - ENV = {args.env.upper()}{' + WRITE PROBE' if args.write_probe else ' (read-only)'} #####")
    print(f"key source: {source} | key kind: {kind} | role: {role} | length: {len(key)}  (key itself never printed)")
    if kind == "secret" or role not in ("anon",):
        sys.exit(f"Refusing: this is not an anon key (kind={kind}, role={role}). The probe must only ever use the anon key.")

    conn = connect(args.env, args.local_url, readonly=True)
    cur = conn.cursor()
    tables = [r[0] for r in q(cur, "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                                    "WHERE n.nspname='public' AND c.relkind IN ('r','p') ORDER BY 1")]
    pks = {}
    for t, col, typ in q(cur, """
            SELECT c.relname, a.attname, ty.typname FROM pg_class c
            JOIN pg_namespace n ON n.oid=c.relnamespace
            JOIN pg_index i ON i.indrelid=c.oid AND i.indisprimary
            JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum = ANY(i.indkey)
            JOIN pg_type ty ON ty.oid=a.atttypid
            WHERE n.nspname='public' AND c.relkind IN ('r','p')"""):
        pks.setdefault(t, []).append((col, typ))
    first_cols = {}
    for t, col in q(cur, "SELECT table_name, column_name FROM information_schema.columns WHERE table_schema='public' ORDER BY table_name, ordinal_position"):
        first_cols.setdefault(t, []).append(col)

    def db_counts():
        return {t: q(cur, f'SELECT count(*) FROM public."{t}"')[0][0] for t in tables}

    before = db_counts()
    client = httpx.Client(timeout=30)

    print("\n--- GET /rest/v1/<table>?select=*&limit=0 (Prefer: count=exact)  [status | rows visible to anon | error code]")
    for t in tables:
        r = client.get(f"{base}/rest/v1/{t}?select=*&limit=0", headers=headers_for(key, kind, {"Prefer": "count=exact"}))
        print(f"{t:22} | {r.status_code} | {count_from(r) if r.status_code < 300 else '-':>6} | {err_code(r)}")

    if args.write_probe:
        print("\n--- PATCH /rest/v1/<table>?<pk>=eq.<impossible>  body {<col>: null}  [status | error code]   (matches 0 rows by construction)")
        for t in tables:
            pk = pks.get(t, [])
            if len(pk) != 1 or pk[0][1] not in IMPOSSIBLE:
                print(f"{t:22} | SKIPPED (pk={pk or 'none'}; no safe impossible filter)")
                continue
            col, typ = pk[0]
            val = IMPOSSIBLE[typ]
            hit = q(cur, f'SELECT count(*) FROM public."{t}" WHERE "{col}" = %s', (val,))[0][0]
            if hit != 0:
                print(f"{t:22} | SKIPPED (safety check: impossible filter matched {hit} row(s) in the DB)")
                continue
            target = next((c for c in first_cols.get(t, []) if c != col), col)
            r = client.patch(f"{base}/rest/v1/{t}?{col}=eq.{val}", json={target: None},
                             headers=headers_for(key, kind, {"Prefer": "return=minimal,count=exact", "Content-Type": "application/json"}))
            verdict = "ACCEPTED (0 rows matched)" if r.status_code in (200, 204) else "DENIED" if r.status_code in (401, 403) else "OTHER"
            print(f"{t:22} | {r.status_code} | {err_code(r):6} | {verdict}")

    after = db_counts()
    print("\n--- row counts before == after all probes (direct read-only connection):", before == after)
    if before != after:
        print("!! DIFFERENCE:", {t: (before[t], after[t]) for t in tables if before[t] != after[t]})
        sys.exit(2)
    conn.close()


if __name__ == "__main__":
    main()
