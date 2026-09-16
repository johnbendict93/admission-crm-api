-- Migration 0007: Soft-delete columns for telecallers
--
-- Extends the same deleted_at/deleted_by soft-delete pattern already
-- applied to leads/applicants/applications (0003), fee_payments (0004),
-- scholarships (0005) and hostel_allotments (0006) to telecallers, ahead
-- of building the /telecallers module.
--
-- No created_by column is added here: live-audited on dev immediately
-- before writing this (information_schema.columns + pg_constraint,
-- Sept 2026) - telecallers has no created_by column, same situation as
-- applications/fee_payments/scholarships/hostel_allotments. No CHECK
-- constraints and no triggers exist on this table either - unlike all
-- six prior modules, telecallers also has no updated_at column, so this
-- migration deliberately does not add one (out of scope: only soft
-- delete was requested).
--
-- deleted_by references public.users(id), same as the other six
-- tables, so it's always a real app user, never a raw auth.users id
-- with no role/name attached.

ALTER TABLE public.telecallers
    ADD COLUMN IF NOT EXISTS deleted_at timestamptz,
    ADD COLUMN IF NOT EXISTS deleted_by uuid REFERENCES public.users(id);

CREATE INDEX IF NOT EXISTS idx_telecallers_not_deleted
    ON public.telecallers (id) WHERE deleted_at IS NULL;
