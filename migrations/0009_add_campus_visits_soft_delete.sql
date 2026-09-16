-- Migration 0009: Soft-delete columns for campus_visits
--
-- Extends the same deleted_at/deleted_by soft-delete pattern used for
-- leads/applicants/applications (0003), fee_payments (0004), scholarships
-- (0005), hostel_allotments (0006), telecallers (0007) and call_schedules
-- (0008) to campus_visits, ahead of building the /campus-visits module.
--
-- Live-audited on dev immediately before writing this (information_schema
-- .columns + pg_constraint, Sept 2026): campus_visits has no is_active
-- column to reuse, no CHECK constraints, no triggers, and no updated_at
-- column, so none of those are touched here. This table IS FK'd to leads
-- (lead_id -> leads.id) and represents a per-lead transactional event
-- record (a campus visit that happened), not static reference/config
-- data - same category as fee_payments/scholarships/hostel_allotments/
-- telecallers/call_schedules, all of which use deleted_at/deleted_by
-- rather than an is_active flag.
--
-- deleted_by references public.users(id), same as every other soft-
-- deleted table, so it's always a real app user.

ALTER TABLE public.campus_visits
    ADD COLUMN IF NOT EXISTS deleted_at timestamptz,
    ADD COLUMN IF NOT EXISTS deleted_by uuid REFERENCES public.users(id);

CREATE INDEX IF NOT EXISTS idx_campus_visits_not_deleted
    ON public.campus_visits (id) WHERE deleted_at IS NULL;
