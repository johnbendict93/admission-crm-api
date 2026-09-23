-- Migration 0019: add fee_due_schedule table
--
-- WHY
--   Module 18 (Fee Default Risk Predictor, ML roadmap) needs to know what an
--   applicant OWES and BY WHEN, not just what they've already paid.
--   fee_payments (audited via app/models/fee_payments.py, Sept 2026) only
--   records payments that actually happened - no due-date/expected-amount/
--   status concept exists anywhere in the live schema. Rather than bolting a
--   due-date onto fee_payments (which would conflate "what's owed" with
--   "what's paid" in one table), this adds a separate schedule table.
--   fee_payments stays exactly as-is. Module 18's label is computed by
--   comparing this table (owed, by when) against fee_payments (actually
--   paid) - not written here, that's the training script's job.
--
--   John chose this over redefining module 18's scope (2026-09-22).
--
-- SHAPE
--   Mirrors fee_payments' column conventions (fee_component text,
--   academic_year text default '2026-27', amount numeric(10,2)) plus the
--   deleted_at/deleted_by soft-delete pattern every other table already has
--   (migrations 0003-0012). No created_by: fee_payments itself has none
--   (0004's audit found the live schema never gave it one), and this table
--   is the same "money on an applicant" domain - not introducing an
--   inconsistent column here either.
--
-- SAFETY (cross-app check done before writing this)
--   * Brand new table - nothing existing references it, so nothing existing
--     can break.
--   * dce_crm (Streamlit) has no code path that touches fee_payments or any
--     fee table; unaffected.
--   * RLS is enabled with NO policy at all (not even a locked-down one) -
--     migration 0015 already set `ALTER DEFAULT PRIVILEGES ... REVOKE ALL
--     ON TABLES FROM anon, authenticated` for the public schema, so this
--     new table inherits zero anon/authenticated privileges automatically.
--     The API's service_role key bypasses RLS as usual; no other client
--     needs access.
--   * Apply to DEV first, verify, then PROD. Apply before deploying any API
--     code that reads/writes this table.
--
-- ROLLBACK: migrations/rollback/0019_rollback_dev.sql / 0019_rollback_prod.sql
--   (drops the table; loses any rows written since).

CREATE TABLE public.fee_due_schedule (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    applicant_id uuid NOT NULL REFERENCES public.applicants(id) ON DELETE CASCADE,
    fee_component text NOT NULL,
    academic_year text DEFAULT '2026-27'::text,
    amount_due numeric(10,2) NOT NULL,
    due_date date NOT NULL,
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now(),
    deleted_at timestamptz,
    deleted_by uuid REFERENCES public.users(id)
);

CREATE INDEX IF NOT EXISTS idx_fee_due_schedule_applicant
    ON public.fee_due_schedule (applicant_id);

CREATE INDEX IF NOT EXISTS idx_fee_due_schedule_not_deleted
    ON public.fee_due_schedule (id) WHERE deleted_at IS NULL;

CREATE TRIGGER fee_due_schedule_updated_at
    BEFORE UPDATE ON public.fee_due_schedule
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();

ALTER TABLE public.fee_due_schedule ENABLE ROW LEVEL SECURITY;
-- Deliberately no policy: service_role (the API) bypasses RLS; everyone
-- else already has zero table privileges via 0015's default-privileges
-- change, so there is nothing for a policy to grant back.
