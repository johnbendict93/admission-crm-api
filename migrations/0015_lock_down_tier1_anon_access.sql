-- Migration 0015: Tier 1 anon/authenticated lockdown (DEV first, then PROD by hand)
--
-- WHY
--   The Sept 2026 dev+prod exposure audit found that `anon` and
--   `authenticated` hold ALL privileges (SELECT/INSERT/UPDATE/DELETE/
--   TRUNCATE/...) on every public table - Supabase's default grants - and
--   that every table also carries a permissive `USING (true) WITH CHECK
--   (true)` policy, so RLS was decorative. The anon key is public by design,
--   so anyone holding it could read, change or delete applicant data and
--   rewrite public.users.role (prod additionally had RLS switched OFF on
--   users, settings, document_types, lookup_values and schema_migrations).
--
-- SCOPE - Tier 1 only: the twelve tables that only the API touches. The API
--   uses the service_role key, which keeps its own grants and bypasses RLS,
--   so nothing the API does changes. dce_crm (Streamlit) references none of
--   these tables in its app code; its only mentions of `users` are two
--   one-off verify scripts (verify_live_deployed_app.py,
--   verify_soft_delete_visibility_fix.py) that will stop working against
--   prod once this is applied there - by design.
--
-- NOT TOUCHED (Tier 2 - dce_crm still needs anon access to these until it is
--   moved to a server-side service key; locked down in a later migration):
--     leads, followups, call_schedules, campus_visits, telecallers
--
-- WHAT IT DOES
--   1. ENABLE ROW LEVEL SECURITY on every Tier 1 table (idempotent; brings
--      prod's five RLS-off tables in line with dev).
--   2. DROP every permissive policy that is a literal `true`
--      (*_all, users_read, users_insert). Policies with a real predicate
--      (auth.uid()-based) are kept: with privileges revoked they are inert
--      and they document the original intent.
--   3. REVOKE ALL on the Tier 1 tables FROM anon, authenticated. service_role
--      and the table owner (postgres) are untouched.
--   4. ALTER DEFAULT PRIVILEGES so future tables created in public by the
--      migration role do not auto-grant to anon/authenticated.
--
-- SAFETY
--   * public.handle_new_auth_user() (auth trigger that inserts into
--     public.users) is SECURITY DEFINER and runs as its owner, which is
--     also users' owner; table owners bypass RLS unless FORCE RLS is set
--     (it is not). Verified on a scratch Postgres replica of dev (roles,
--     default grants, RLS, policies - including an owner WITHOUT BYPASSRLS)
--     and, on the real database, by check 7 of
--     migrations/0015_tools/verify_lockdown.py (rolled-back test insert).
--   * migrations/run_migrations.py connects as `postgres.<project-ref>` (the
--     `postgres` role via the Supabase pooler), which is expected to own
--     schema_migrations; owners bypass RLS, so enabling RLS there does not
--     block the runner. check_0015_preflight.py (c4) shows the real owner.
--   * ROLLBACK: take the snapshot BEFORE applying, per environment:
--         python migrations/0015_tools/snapshot_state.py --env dev
--     which writes migrations/rollback/0015_rollback_dev.sql from the LIVE
--     grants/policies/RLS state. Do the same with --env prod before prod.
--     Never reuse dev's rollback file on prod (the two states differ).
--   * Every statement is idempotent, so a partial re-run is harmless.
--
-- APPLY (dev first, verify, only then prod):
--     python migrations/run_migrations.py apply --env dev
--     python migrations/0015_tools/verify_lockdown.py --env dev

-- 1. Enable RLS on every Tier 1 table
ALTER TABLE public.applicants ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.applications ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.counseling_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.document_types ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.fee_payments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.follow_ups ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.hostel_allotments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.lookup_values ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.schema_migrations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.scholarships ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;

-- 2. Drop the permissive literal-true policies
DROP POLICY IF EXISTS applicants_all ON public.applicants;
DROP POLICY IF EXISTS applications_all ON public.applications;
DROP POLICY IF EXISTS counseling_sessions_all ON public.counseling_sessions;
DROP POLICY IF EXISTS document_types_all ON public.document_types;
DROP POLICY IF EXISTS fee_payments_all ON public.fee_payments;
DROP POLICY IF EXISTS follow_ups_all ON public.follow_ups;
DROP POLICY IF EXISTS hostel_allotments_all ON public.hostel_allotments;
DROP POLICY IF EXISTS lookup_values_all ON public.lookup_values;
DROP POLICY IF EXISTS scholarships_all ON public.scholarships;
DROP POLICY IF EXISTS settings_all ON public.settings;
DROP POLICY IF EXISTS users_all ON public.users;
DROP POLICY IF EXISTS users_read ON public.users;
DROP POLICY IF EXISTS users_insert ON public.users;

-- 3. Revoke every privilege from the public-facing roles
REVOKE ALL ON TABLE public.applicants FROM anon, authenticated;
REVOKE ALL ON TABLE public.applications FROM anon, authenticated;
REVOKE ALL ON TABLE public.counseling_sessions FROM anon, authenticated;
REVOKE ALL ON TABLE public.document_types FROM anon, authenticated;
REVOKE ALL ON TABLE public.fee_payments FROM anon, authenticated;
REVOKE ALL ON TABLE public.follow_ups FROM anon, authenticated;
REVOKE ALL ON TABLE public.hostel_allotments FROM anon, authenticated;
REVOKE ALL ON TABLE public.lookup_values FROM anon, authenticated;
REVOKE ALL ON TABLE public.schema_migrations FROM anon, authenticated;
REVOKE ALL ON TABLE public.scholarships FROM anon, authenticated;
REVOKE ALL ON TABLE public.settings FROM anon, authenticated;
REVOKE ALL ON TABLE public.users FROM anon, authenticated;

-- 4. Future tables created by this role in public must not auto-grant
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM anon, authenticated;
