-- Migration 0004: Soft-delete columns for fee_payments
--
-- Extends the same deleted_at/deleted_by soft-delete pattern already
-- applied to leads/applicants/applications (migration 0003) to
-- fee_payments, ahead of building the /fee-payments module.
--
-- No created_by column is added here: live-audited on dev immediately
-- before writing this (information_schema.columns + pg_constraint,
-- Sept 2026) - fee_payments has no created_by column, the same situation
-- "applications" is already in (it has no created_by either, and its
-- service layer never sets one). Not every table in the original
-- Streamlit-era schema got a created_by column, and this migration
-- doesn't introduce one where the live schema doesn't already call for
-- it.
--
-- deleted_by references public.users(id), same as the other three
-- tables, so it's always a real app user, never a raw auth.users id
-- with no role/name attached.

ALTER TABLE public.fee_payments
    ADD COLUMN IF NOT EXISTS deleted_at timestamptz,
    ADD COLUMN IF NOT EXISTS deleted_by uuid REFERENCES public.users(id);

CREATE INDEX IF NOT EXISTS idx_fee_payments_not_deleted
    ON public.fee_payments (id) WHERE deleted_at IS NULL;
