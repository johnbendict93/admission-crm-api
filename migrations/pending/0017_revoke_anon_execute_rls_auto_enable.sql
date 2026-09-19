-- Migration 0017: revoke anon/authenticated EXECUTE on public.rls_auto_enable()
--                 ***  DRAFT - NOT APPLIED  ***
--
-- STATUS: DRAFT, in migrations/pending/ (not discovered by run_migrations.py).
--   Not applied to dev or prod. INDEPENDENT of 0016: it has no dce_crm
--   dependency and may be released on its own (the runner applies whatever is
--   in migrations/ that is not yet recorded, in any order).
--
-- WHY
--   migrations/0016_tools/rpc_probe.py (dev, anon key) showed that of the five
--   public functions anon may EXECUTE, four are trigger functions that
--   PostgREST does not expose (404 / PGRST202) - no action needed - but
--   public.rls_auto_enable() (an event-trigger function, SECURITY DEFINER)
--   IS reachable: POST /rest/v1/rpc/rls_auto_enable returned 400 / 0A000
--   ("event trigger functions can only be called as event triggers"), i.e.
--   the function is invoked and then refuses. That is harmless in practice
--   (it cannot run outside an event trigger) but a SECURITY DEFINER function
--   should not be callable by the public roles at all.
--   The function appeared on DEV only; the prod audit listed just the four
--   trigger functions. The guard below makes this a no-op wherever the
--   function does not exist, so the same file is safe on prod.
--
-- WHAT IT DOES
--   Revokes EXECUTE on public.rls_auto_enable() from PUBLIC, anon and
--   authenticated. Event triggers do not check EXECUTE when they fire (only
--   when created, by a superuser), so this cannot stop the event trigger.
--   service_role and the owner keep their own privileges.
--
-- BEFORE APPLYING (read-only): record owner + ACL for the rollback, e.g.
--     python check_tier2_audit.py --env dev        (section 6)
--   If the owner is NOT the migration role (postgres), REVOKE may only warn
--   ("no privileges could be revoked"); the verify query below will show it.
-- ROLLBACK (restores the usual Supabase default; adjust to the recorded ACL):
--     GRANT EXECUTE ON FUNCTION public.rls_auto_enable() TO PUBLIC, anon, authenticated;
-- VERIFY (expect false, false):
--     SELECT has_function_privilege('anon','public.rls_auto_enable()','EXECUTE'),
--            has_function_privilege('authenticated','public.rls_auto_enable()','EXECUTE');
--   then: python migrations/0016_tools/rpc_probe.py --env dev   (expect 401/404, not 400/0A000)

DO $$
BEGIN
  IF to_regprocedure('public.rls_auto_enable()') IS NOT NULL THEN
    REVOKE EXECUTE ON FUNCTION public.rls_auto_enable() FROM PUBLIC, anon, authenticated;
  END IF;
END
$$;
