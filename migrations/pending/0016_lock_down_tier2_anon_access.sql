-- Migration 0016: Tier 2 anon/authenticated lockdown  ***  DRAFT - NOT APPLIED  ***
--
-- STATUS: DRAFT. Lives in migrations/pending/ ON PURPOSE. run_migrations.py
--   only discovers migrations/*.sql (non-recursive), so no `apply` run - for
--   this or any later migration - can pick it up by accident. It has NOT
--   been applied to dev or prod. To release it, git mv it into migrations/
--   in the same change that applies it, after every precondition below.
--
-- !! PRECONDITION - DO NOT APPLY UNTIL EVERY dce_crm CONSUMER USES A
-- !! SERVER-SIDE service_role KEY. This migration removes ALL access for the
-- !! anon key on the five tables dce_crm reads and writes. With the anon key
-- !! still in place dce_crm stops working (reads return 401, writes fail).
-- !! Consumers that must be switched first (see the Tier 2 investigation):
-- !!   1. the Streamlit app (Streamlit Cloud secrets: SUPABASE_KEY)
-- !!   2. scheduler.py (daily-report process; reads the same secrets file)
-- !!   3. the two one-off verify_*.py scripts (optional; they also read users)
-- !! Sequence: dev swap+test -> dev 0016 -> prod key swap -> verify dce_crm
-- !!            works on the service key -> prod 0016.
--
-- WHY
--   0015 closed the twelve Tier 1 tables. The five Tier 2 tables are still
--   readable AND writable by anyone holding the public anon key (all
--   privileges granted to anon and authenticated, plus an `allow_all`
--   USING (true) WITH CHECK (true) policy on each), and the anon key ships
--   inside dce_crm. On prod that is the leads, follow-up call notes, call
--   schedules, campus visits and telecaller records.
--
-- SCOPE - exactly these five tables:
--     leads, followups, call_schedules, campus_visits, telecallers
--   Tier 1 was handled by 0015 and is not touched here. Default privileges
--   were already changed in 0015 and are not touched here.
--
-- WHAT IT DOES
--   1. ENABLE ROW LEVEL SECURITY (already on; idempotent, documents intent).
--   2. DROP the `allow_all` (true/true) policy on each table.
--   3. REVOKE ALL on each table FROM anon, authenticated (BOTH roles: any
--      signed-in account is `authenticated`, and it had full access too).
--   service_role (the key dce_crm moves to) and the table owner (postgres)
--   are untouched; service_role bypasses RLS and keeps its own grants.
--
-- ROLLBACK: take the snapshot BEFORE applying, per environment:
--         python migrations/0016_tools/snapshot_tier2.py --env dev
--   which writes migrations/rollback/0016_rollback_<env>.sql from the LIVE
--   grants/policies/RLS state. Never reuse one environment's file on the other.
--   Every statement here is idempotent, so a partial re-run is harmless.
--
-- VERIFY (after apply):
--         python migrations/0016_tools/verify_tier2_lockdown.py --env dev
--         python migrations/0016_tools/verify_tier2_lockdown.py --env prod --read-only-only
--         python migrations/0015_tools/anon_probe.py --env <env>   # all 17 tables denied

-- 1. Enable RLS on every Tier 2 table
ALTER TABLE public.leads ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.followups ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.call_schedules ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.campus_visits ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.telecallers ENABLE ROW LEVEL SECURITY;

-- 2. Drop the permissive allow_all (true/true) policies
DROP POLICY IF EXISTS allow_all ON public.leads;
DROP POLICY IF EXISTS allow_all ON public.followups;
DROP POLICY IF EXISTS allow_all ON public.call_schedules;
DROP POLICY IF EXISTS allow_all ON public.campus_visits;
DROP POLICY IF EXISTS allow_all ON public.telecallers;

-- 3. Revoke every privilege from the public-facing roles
REVOKE ALL ON TABLE public.leads FROM anon, authenticated;
REVOKE ALL ON TABLE public.followups FROM anon, authenticated;
REVOKE ALL ON TABLE public.call_schedules FROM anon, authenticated;
REVOKE ALL ON TABLE public.campus_visits FROM anon, authenticated;
REVOKE ALL ON TABLE public.telecallers FROM anon, authenticated;
