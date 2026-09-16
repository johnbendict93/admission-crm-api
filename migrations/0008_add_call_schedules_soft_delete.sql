-- Migration 0008: Soft-delete columns for call_schedules
--
-- Extends the same deleted_at/deleted_by soft-delete pattern used for
-- leads/applicants/applications (0003), fee_payments (0004), scholarships
-- (0005), hostel_allotments (0006) and telecallers (0007) to
-- call_schedules, ahead of building the /call-schedules module.
--
-- Live-audited on dev immediately before writing this (information_schema
-- .columns + pg_constraint, Sept 2026): call_schedules has no is_active
-- column to reuse (unlike document_types/lookup_values), no CHECK
-- constraints, no triggers, and no updated_at column, so none of those
-- are touched here. This table IS FK'd to leads (lead_id -> leads.id)
-- and represents a per-lead transactional event record (a scheduled
-- call), not static reference/config data - the same category as
-- fee_payments/scholarships/hostel_allotments/telecallers, all of which
-- use deleted_at/deleted_by rather than an is_active flag.
--
-- deleted_by references public.users(id), same as every other soft-
-- deleted table, so it's always a real app user.

ALTER TABLE public.call_schedules
    ADD COLUMN IF NOT EXISTS deleted_at timestamptz,
    ADD COLUMN IF NOT EXISTS deleted_by uuid REFERENCES public.users(id);

CREATE INDEX IF NOT EXISTS idx_call_schedules_not_deleted
    ON public.call_schedules (id) WHERE deleted_at IS NULL;
