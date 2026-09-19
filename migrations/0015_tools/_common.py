"""Shared helpers for the migration-0015 tooling (snapshot / verify / anon
probe). Kept here rather than in app/ because nothing in the running API
should ever depend on it.

TIER 1 = tables the anon key must NOT be able to reach at all: only the API
touches them, and the API uses the service_role key (which bypasses RLS and
keeps its own grants). Confirmed by the Sept 2026 dev+prod identity/exposure
audit and a grep of dce_crm (see migrations/0015_*.sql header).

TIER 2 = tables dce_crm (Streamlit) still reads/writes with the anon key.
0015 deliberately does NOT touch them; they are locked down later, only
after dce_crm has been moved to a server-side service key.
"""
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

TIER1_TABLES = [
    "applicants",
    "applications",
    "counseling_sessions",
    "document_types",
    "fee_payments",
    "follow_ups",
    "hostel_allotments",
    "lookup_values",
    "schema_migrations",
    "scholarships",
    "settings",
    "users",
]

TIER2_TABLES = [
    "call_schedules",
    "campus_visits",
    "followups",
    "leads",
    "telecallers",
]

# Policies 0015 drops: every permissive policy whose expression is a literal
# `true` (i.e. "anyone may do anything"). Policies with a real predicate
# (auth.uid()-based) are intentionally kept - with anon/authenticated
# privileges revoked they are inert, and they document the original intent.
TRUE_POLICIES = {
    "applicants": ["applicants_all"],
    "applications": ["applications_all"],
    "counseling_sessions": ["counseling_sessions_all"],
    "document_types": ["document_types_all"],
    "fee_payments": ["fee_payments_all"],
    "follow_ups": ["follow_ups_all"],
    "hostel_allotments": ["hostel_allotments_all"],
    "lookup_values": ["lookup_values_all"],
    "scholarships": ["scholarships_all"],
    "settings": ["settings_all"],
    "users": ["users_all", "users_read", "users_insert"],
}

TABLE_PRIVS = ["SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"]


def _is_loopback(url: str) -> bool:
    if "host=/" in url:  # unix-socket style URI used by the local scratch server
        return True
    m = re.match(r"postgres(?:ql)?://[^@]*@?([^:/?]+)", url)
    return bool(m) and m.group(1) in ("localhost", "127.0.0.1", "::1", "")


def get_database_url(env: str, local_url: str | None = None) -> str:
    """local_url exists only so the tooling can be exercised against a
    throw-away Postgres on this machine; it is refused unless it points at
    loopback / a unix socket, so it can never be used to reach a real
    Supabase project by accident."""
    if local_url:
        if not _is_loopback(local_url):
            sys.exit("--local-url must point at localhost / a unix socket. Refusing.")
        return local_url
    from app.core.config import settings

    url = settings.DEV_DATABASE_URL if env == "dev" else settings.PROD_DATABASE_URL
    if not url:
        sys.exit(f"{env.upper()}_DATABASE_URL is empty in .env")
    return url


def connect(env: str, local_url: str | None = None, readonly: bool = True):
    import psycopg2

    conn = psycopg2.connect(get_database_url(env, local_url))
    if readonly:
        conn.set_session(readonly=True, autocommit=True)
    else:
        conn.autocommit = False
    return conn


def q(cur, sql, params=None):
    cur.execute(sql, params)
    return cur.fetchall()


def show(cur, title, sql, params=None):
    """Print a query result as `col | col` rows. Never raises: a failed
    query is reported as COULD NOT CHECK so nothing is silently skipped."""
    print(f"\n--- {title}")
    try:
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        print(" | ".join(cols))
        if not rows:
            print("(0 rows)")
        for r in rows:
            print(" | ".join("NULL" if v is None else str(v) for v in r))
        return rows
    except Exception as e:
        print(f"!! COULD NOT CHECK: {type(e).__name__}: {str(e).strip().splitlines()[0]}")
        return None
