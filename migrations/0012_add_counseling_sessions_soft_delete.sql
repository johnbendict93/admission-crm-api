-- Migration 0012: Soft-delete columns for counseling_sessions
--
-- Extends the same deleted_at/deleted_by soft-delete pattern already
-- applied to leads/applicants/applications (0003), fee_payments (0004),
-- scholarships (0005), hostel_allotments (0006), telecallers (0007),
-- call_schedules (0008), campus_visits (0009) and followups (0010) to
-- counseling_sessions, ahead of building the /counseling-sessions
-- module - the 14th and final table on the original list.
--
-- Judgment call: soft-delete, not is_active. This is a transactional,
-- per-applicant event record (a logged counseling session), the same
-- category as fee_payments/scholarships/hostel_allotments, not a
-- config/reference table like settings/document_types/lookup_values.
--
-- Unlike settings (0011), no updated_at trigger is added here: live-
-- audited on dev immediately before writing this (information_schema.
-- columns + pg_constraint + pg_trigger, Sept 2026) - counseling_sessions
-- already has its own trigger (trg_sessions_updated_at), present since
-- the initial schema, so there's no gap to fix.
--
-- No created_by column is added: same live audit found none exists,
-- same situation as most prior modules. This table also has zero live
-- Streamlit dependency (grepped dce_crm - no reference to "counseling"
-- anywhere), so unlike followups/call_schedules/campus_visits/
-- telecallers there is no cross-app visibility gap to worry about.
--
-- deleted_by references public.users(id), same as every prior
-- soft-deleted table.

ALTER TABLE public.counseling_sessions
    ADD COLUMN IF NOT EXISTS deleted_at timestamptz,
    ADD COLUMN IF NOT EXISTS deleted_by uuid REFERENCES public.users(id);

CREATE INDEX IF NOT EXISTS idx_counseling_sessions_not_deleted
    ON public.counseling_sessions (id) WHERE deleted_at IS NULL;
