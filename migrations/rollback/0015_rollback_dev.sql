-- ROLLBACK for migration 0015 - restores the DEV state captured by
-- migrations/0015_tools/snapshot_state.py at 2026-09-19T14:16:36+00:00 (connected as postgres).
-- Generated from the LIVE database BEFORE 0015 was applied. Apply with the SAME environment only:
--     psql / any client on the DEV DATABASE_URL, run this file as one transaction.
-- STATE_FINGERPRINT=3d7714783cff28b543e80fca218cd86e9af3830e007a064be7146f9eb46da8cb

BEGIN;

-- applicants: owner=postgres rls=True force_rls=False
-- applications: owner=postgres rls=True force_rls=False
-- counseling_sessions: owner=postgres rls=True force_rls=False
-- document_types: owner=postgres rls=True force_rls=False
-- fee_payments: owner=postgres rls=True force_rls=False
-- follow_ups: owner=postgres rls=True force_rls=False
-- hostel_allotments: owner=postgres rls=True force_rls=False
-- lookup_values: owner=postgres rls=True force_rls=False
-- schema_migrations: owner=postgres rls=True force_rls=False
-- scholarships: owner=postgres rls=True force_rls=False
-- settings: owner=postgres rls=True force_rls=False
-- users: owner=postgres rls=True force_rls=False

-- Policies: drop every policy recorded (so re-creation cannot collide), then re-create.
DROP POLICY IF EXISTS "Counselors see assigned applicants" ON public."applicants";
DROP POLICY IF EXISTS "applicants_all" ON public."applicants";
DROP POLICY IF EXISTS "Staff can manage applications" ON public."applications";
DROP POLICY IF EXISTS "applications_all" ON public."applications";
DROP POLICY IF EXISTS "Counselors manage own sessions" ON public."counseling_sessions";
DROP POLICY IF EXISTS "counseling_sessions_all" ON public."counseling_sessions";
DROP POLICY IF EXISTS "document_types_all" ON public."document_types";
DROP POLICY IF EXISTS "fee_payments_all" ON public."fee_payments";
DROP POLICY IF EXISTS "Users manage own follow-ups" ON public."follow_ups";
DROP POLICY IF EXISTS "follow_ups_all" ON public."follow_ups";
DROP POLICY IF EXISTS "hostel_allotments_all" ON public."hostel_allotments";
DROP POLICY IF EXISTS "lookup_values_all" ON public."lookup_values";
DROP POLICY IF EXISTS "scholarships_all" ON public."scholarships";
DROP POLICY IF EXISTS "settings_all" ON public."settings";
DROP POLICY IF EXISTS "Admins can read all users" ON public."users";
DROP POLICY IF EXISTS "Users can read own record" ON public."users";
DROP POLICY IF EXISTS "users_all" ON public."users";
DROP POLICY IF EXISTS "users_insert" ON public."users";
DROP POLICY IF EXISTS "users_read" ON public."users";
DROP POLICY IF EXISTS "users_update" ON public."users";
CREATE POLICY "Counselors see assigned applicants" ON public."applicants" AS PERMISSIVE FOR ALL TO PUBLIC USING (((assigned_counselor = auth.uid()) OR (EXISTS ( SELECT 1
   FROM users
  WHERE ((users.id = auth.uid()) AND (users.role = ANY (ARRAY['admin'::text, 'staff'::text])))))));
CREATE POLICY "applicants_all" ON public."applicants" AS PERMISSIVE FOR ALL TO PUBLIC USING (true) WITH CHECK (true);
CREATE POLICY "Staff can manage applications" ON public."applications" AS PERMISSIVE FOR ALL TO PUBLIC USING ((EXISTS ( SELECT 1
   FROM users
  WHERE ((users.id = auth.uid()) AND (users.role = ANY (ARRAY['admin'::text, 'staff'::text, 'counselor'::text]))))));
CREATE POLICY "applications_all" ON public."applications" AS PERMISSIVE FOR ALL TO PUBLIC USING (true) WITH CHECK (true);
CREATE POLICY "Counselors manage own sessions" ON public."counseling_sessions" AS PERMISSIVE FOR ALL TO PUBLIC USING (((counselor_id = auth.uid()) OR (EXISTS ( SELECT 1
   FROM users
  WHERE ((users.id = auth.uid()) AND (users.role = ANY (ARRAY['admin'::text, 'staff'::text])))))));
CREATE POLICY "counseling_sessions_all" ON public."counseling_sessions" AS PERMISSIVE FOR ALL TO PUBLIC USING (true) WITH CHECK (true);
CREATE POLICY "document_types_all" ON public."document_types" AS PERMISSIVE FOR ALL TO PUBLIC USING (true) WITH CHECK (true);
CREATE POLICY "fee_payments_all" ON public."fee_payments" AS PERMISSIVE FOR ALL TO PUBLIC USING (true) WITH CHECK (true);
CREATE POLICY "Users manage own follow-ups" ON public."follow_ups" AS PERMISSIVE FOR ALL TO PUBLIC USING (((assigned_to = auth.uid()) OR (created_by = auth.uid()) OR (EXISTS ( SELECT 1
   FROM users
  WHERE ((users.id = auth.uid()) AND (users.role = ANY (ARRAY['admin'::text, 'staff'::text])))))));
CREATE POLICY "follow_ups_all" ON public."follow_ups" AS PERMISSIVE FOR ALL TO PUBLIC USING (true) WITH CHECK (true);
CREATE POLICY "hostel_allotments_all" ON public."hostel_allotments" AS PERMISSIVE FOR ALL TO PUBLIC USING (true) WITH CHECK (true);
CREATE POLICY "lookup_values_all" ON public."lookup_values" AS PERMISSIVE FOR ALL TO PUBLIC USING (true) WITH CHECK (true);
CREATE POLICY "scholarships_all" ON public."scholarships" AS PERMISSIVE FOR ALL TO PUBLIC USING (true) WITH CHECK (true);
CREATE POLICY "settings_all" ON public."settings" AS PERMISSIVE FOR ALL TO PUBLIC USING (true) WITH CHECK (true);
CREATE POLICY "Admins can read all users" ON public."users" AS PERMISSIVE FOR SELECT TO PUBLIC USING ((EXISTS ( SELECT 1
   FROM users users_1
  WHERE ((users_1.id = auth.uid()) AND (users_1.role = 'admin'::text)))));
CREATE POLICY "Users can read own record" ON public."users" AS PERMISSIVE FOR SELECT TO PUBLIC USING ((auth.uid() = id));
CREATE POLICY "users_all" ON public."users" AS PERMISSIVE FOR ALL TO PUBLIC USING (true) WITH CHECK (true);
CREATE POLICY "users_insert" ON public."users" AS PERMISSIVE FOR INSERT TO PUBLIC WITH CHECK (true);
CREATE POLICY "users_read" ON public."users" AS PERMISSIVE FOR SELECT TO PUBLIC USING (true);
CREATE POLICY "users_update" ON public."users" AS PERMISSIVE FOR UPDATE TO PUBLIC USING ((auth.uid() = id));

-- RLS / FORCE RLS exactly as recorded.
ALTER TABLE public."applicants" ENABLE ROW LEVEL SECURITY;
ALTER TABLE public."applicants" NO FORCE ROW LEVEL SECURITY;
ALTER TABLE public."applications" ENABLE ROW LEVEL SECURITY;
ALTER TABLE public."applications" NO FORCE ROW LEVEL SECURITY;
ALTER TABLE public."counseling_sessions" ENABLE ROW LEVEL SECURITY;
ALTER TABLE public."counseling_sessions" NO FORCE ROW LEVEL SECURITY;
ALTER TABLE public."document_types" ENABLE ROW LEVEL SECURITY;
ALTER TABLE public."document_types" NO FORCE ROW LEVEL SECURITY;
ALTER TABLE public."fee_payments" ENABLE ROW LEVEL SECURITY;
ALTER TABLE public."fee_payments" NO FORCE ROW LEVEL SECURITY;
ALTER TABLE public."follow_ups" ENABLE ROW LEVEL SECURITY;
ALTER TABLE public."follow_ups" NO FORCE ROW LEVEL SECURITY;
ALTER TABLE public."hostel_allotments" ENABLE ROW LEVEL SECURITY;
ALTER TABLE public."hostel_allotments" NO FORCE ROW LEVEL SECURITY;
ALTER TABLE public."lookup_values" ENABLE ROW LEVEL SECURITY;
ALTER TABLE public."lookup_values" NO FORCE ROW LEVEL SECURITY;
ALTER TABLE public."schema_migrations" ENABLE ROW LEVEL SECURITY;
ALTER TABLE public."schema_migrations" NO FORCE ROW LEVEL SECURITY;
ALTER TABLE public."scholarships" ENABLE ROW LEVEL SECURITY;
ALTER TABLE public."scholarships" NO FORCE ROW LEVEL SECURITY;
ALTER TABLE public."settings" ENABLE ROW LEVEL SECURITY;
ALTER TABLE public."settings" NO FORCE ROW LEVEL SECURITY;
ALTER TABLE public."users" ENABLE ROW LEVEL SECURITY;
ALTER TABLE public."users" NO FORCE ROW LEVEL SECURITY;

-- Grants to anon / authenticated exactly as recorded (REVOKE first so the result is exact).
REVOKE ALL ON TABLE public."applicants" FROM anon, authenticated;
REVOKE ALL ON TABLE public."applications" FROM anon, authenticated;
REVOKE ALL ON TABLE public."counseling_sessions" FROM anon, authenticated;
REVOKE ALL ON TABLE public."document_types" FROM anon, authenticated;
REVOKE ALL ON TABLE public."fee_payments" FROM anon, authenticated;
REVOKE ALL ON TABLE public."follow_ups" FROM anon, authenticated;
REVOKE ALL ON TABLE public."hostel_allotments" FROM anon, authenticated;
REVOKE ALL ON TABLE public."lookup_values" FROM anon, authenticated;
REVOKE ALL ON TABLE public."schema_migrations" FROM anon, authenticated;
REVOKE ALL ON TABLE public."scholarships" FROM anon, authenticated;
REVOKE ALL ON TABLE public."settings" FROM anon, authenticated;
REVOKE ALL ON TABLE public."users" FROM anon, authenticated;
GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE public."applicants" TO "anon";
GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE public."applicants" TO "authenticated";
GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE public."applications" TO "anon";
GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE public."applications" TO "authenticated";
GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE public."counseling_sessions" TO "anon";
GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE public."counseling_sessions" TO "authenticated";
GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE public."document_types" TO "anon";
GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE public."document_types" TO "authenticated";
GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE public."fee_payments" TO "anon";
GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE public."fee_payments" TO "authenticated";
GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE public."follow_ups" TO "anon";
GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE public."follow_ups" TO "authenticated";
GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE public."hostel_allotments" TO "anon";
GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE public."hostel_allotments" TO "authenticated";
GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE public."lookup_values" TO "anon";
GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE public."lookup_values" TO "authenticated";
GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE public."schema_migrations" TO "anon";
GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE public."schema_migrations" TO "authenticated";
GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE public."scholarships" TO "anon";
GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE public."scholarships" TO "authenticated";
GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE public."settings" TO "anon";
GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE public."settings" TO "authenticated";
GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE public."users" TO "anon";
GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE public."users" TO "authenticated";

-- Default privileges in schema public for anon/authenticated (0015 revoked these for the migration role).
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA public GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLES TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA public GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLES TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "supabase_admin" IN SCHEMA public GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLES TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "supabase_admin" IN SCHEMA public GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLES TO "authenticated";

COMMIT;
