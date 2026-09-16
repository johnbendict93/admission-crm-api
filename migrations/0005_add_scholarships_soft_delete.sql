-- Migration 0005: Soft-delete columns for scholarships
--
-- Extends the same deleted_at/deleted_by soft-delete pattern already
-- applied to leads/applicants/applications (0003) and fee_payments (0004)
-- to scholarships, ahead of building the /scholarships module.
--
-- No created_by column is added here: live-audited on dev immediately
-- before writing this (information_schema.columns + pg_constraint,
-- Sept 2026) - scholarships has no created_by column, same situation as
-- "applications" and "fee_payments". No CHECK constraints exist on this
-- table either - scholarship_type/status are plain text, not restricted
-- to a fixed set at the DB level.
--
-- deleted_by references public.users(id), same as the other four
-- tables, so it's always a real app user, never a raw auth.users id
-- with no role/name attached.

ALTER TABLE public.scholarships
    ADD COLUMN IF NOT EXISTS deleted_at timestamptz,
    ADD COLUMN IF NOT EXISTS deleted_by uuid REFERENCES public.users(id);

CREATE INDEX IF NOT EXISTS idx_scholarships_not_deleted
    ON public.scholarships (id) WHERE deleted_at IS NULL;
