-- ROLLBACK for migration 0016 - restores the PROD state captured by
-- migrations/0016_tools/snapshot_tier2.py at 2026-09-20T07:15:53+00:00 (connected as postgres).
-- Generated from the LIVE database BEFORE 0016 was applied (0016 is a DRAFT until then).
-- Apply to the SAME environment only, as one transaction. Then delete the 0016 row from schema_migrations.
-- STATE_FINGERPRINT=bc797b0f46bd3ed12f81b155c1cb65ed793ef083769d5f3f24ac8ec35351db4e

BEGIN;

-- call_schedules: owner=postgres rls=True force_rls=False
-- campus_visits: owner=postgres rls=True force_rls=False
-- followups: owner=postgres rls=True force_rls=False
-- leads: owner=postgres rls=True force_rls=False
-- telecallers: owner=postgres rls=True force_rls=False

-- Policies: drop every recorded policy (so re-creation cannot collide), then re-create.
DROP POLICY IF EXISTS "allow_all" ON public."call_schedules";
DROP POLICY IF EXISTS "allow_all" ON public."campus_visits";
DROP POLICY IF EXISTS "allow_all" ON public."followups";
DROP POLICY IF EXISTS "allow_all" ON public."leads";
DROP POLICY IF EXISTS "allow_all" ON public."telecallers";
CREATE POLICY "allow_all" ON public."call_schedules" AS PERMISSIVE FOR ALL TO PUBLIC USING (true) WITH CHECK (true);
CREATE POLICY "allow_all" ON public."campus_visits" AS PERMISSIVE FOR ALL TO PUBLIC USING (true) WITH CHECK (true);
CREATE POLICY "allow_all" ON public."followups" AS PERMISSIVE FOR ALL TO PUBLIC USING (true) WITH CHECK (true);
CREATE POLICY "allow_all" ON public."leads" AS PERMISSIVE FOR ALL TO PUBLIC USING (true) WITH CHECK (true);
CREATE POLICY "allow_all" ON public."telecallers" AS PERMISSIVE FOR ALL TO PUBLIC USING (true) WITH CHECK (true);

-- RLS / FORCE RLS exactly as recorded.
ALTER TABLE public."call_schedules" ENABLE ROW LEVEL SECURITY;
ALTER TABLE public."call_schedules" NO FORCE ROW LEVEL SECURITY;
ALTER TABLE public."campus_visits" ENABLE ROW LEVEL SECURITY;
ALTER TABLE public."campus_visits" NO FORCE ROW LEVEL SECURITY;
ALTER TABLE public."followups" ENABLE ROW LEVEL SECURITY;
ALTER TABLE public."followups" NO FORCE ROW LEVEL SECURITY;
ALTER TABLE public."leads" ENABLE ROW LEVEL SECURITY;
ALTER TABLE public."leads" NO FORCE ROW LEVEL SECURITY;
ALTER TABLE public."telecallers" ENABLE ROW LEVEL SECURITY;
ALTER TABLE public."telecallers" NO FORCE ROW LEVEL SECURITY;

-- Grants to anon / authenticated exactly as recorded (REVOKE first so the result is exact).
REVOKE ALL ON TABLE public."call_schedules" FROM anon, authenticated;
REVOKE ALL ON TABLE public."campus_visits" FROM anon, authenticated;
REVOKE ALL ON TABLE public."followups" FROM anon, authenticated;
REVOKE ALL ON TABLE public."leads" FROM anon, authenticated;
REVOKE ALL ON TABLE public."telecallers" FROM anon, authenticated;
GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE public."call_schedules" TO "anon";
GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE public."call_schedules" TO "authenticated";
GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE public."campus_visits" TO "anon";
GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE public."campus_visits" TO "authenticated";
GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE public."followups" TO "anon";
GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE public."followups" TO "authenticated";
GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE public."leads" TO "anon";
GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE public."leads" TO "authenticated";
GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE public."telecallers" TO "anon";
GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE public."telecallers" TO "authenticated";

COMMIT;
