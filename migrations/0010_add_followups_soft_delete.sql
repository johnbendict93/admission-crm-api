-- Migration 0010: Soft-delete columns for followups
--
-- Extends the same deleted_at/deleted_by soft-delete pattern used for
-- leads/applicants/applications (0003), fee_payments (0004), scholarships
-- (0005), hostel_allotments (0006), telecallers (0007), call_schedules
-- (0008) and campus_visits (0009) to followups, ahead of building the
-- /followups module.
--
-- Live-audited on dev immediately before writing this (information_schema
-- .columns + pg_constraint, Sept 2026): followups has no is_active
-- column to reuse, no CHECK constraints, no triggers, and no updated_at
-- column, so none of those are touched here. This table IS FK'd to leads
-- (lead_id -> leads.id) and represents a per-lead transactional event
-- record (a follow-up call that was logged), not static reference/config
-- data - same category as call_schedules/campus_visits.
--
-- IMPORTANT: unlike every other module built so far, followups is a
-- table the live Streamlit app (dce_crm) actively reads from and writes
-- to today. Confirmed safe to add these columns without breaking that
-- app: every Streamlit read goes through select("*") (picks up the two
-- new nullable columns harmlessly) and the one insert site
-- (pages/5_Followup_Tracking.py) sends a fixed dict of the seven
-- pre-existing columns only, with no dependency on the table's exact
-- column set. Both new columns are nullable with no default requirement,
-- so neither read nor insert paths break. Note (not a migration concern,
-- but recorded here for anyone touching this table later): the Streamlit
-- app's queries do not filter on deleted_at, so a followup soft-deleted
-- through the new API will still appear in the Streamlit app's UI/
-- reports until that app is retired or updated to filter it out too.
--
-- deleted_by references public.users(id), same as every other soft-
-- deleted table, so it's always a real app user.

ALTER TABLE public.followups
    ADD COLUMN IF NOT EXISTS deleted_at timestamptz,
    ADD COLUMN IF NOT EXISTS deleted_by uuid REFERENCES public.users(id);

CREATE INDEX IF NOT EXISTS idx_followups_not_deleted
    ON public.followups (id) WHERE deleted_at IS NULL;
