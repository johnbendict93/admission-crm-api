-- Migration 0006: Soft-delete columns for hostel_allotments
--
-- Extends the same deleted_at/deleted_by soft-delete pattern already
-- applied to leads/applicants/applications (0003), fee_payments (0004)
-- and scholarships (0005) to hostel_allotments, ahead of building the
-- /hostel-allotments module.
--
-- No created_by column is added here: live-audited on dev immediately
-- before writing this (information_schema.columns + pg_constraint,
-- Sept 2026) - hostel_allotments has no created_by column, same
-- situation as applications/fee_payments/scholarships. No CHECK
-- constraints exist on this table either - block_name/room_type/status
-- are plain text, not restricted to a fixed set at the DB level.
--
-- deleted_by references public.users(id), same as the other five
-- tables, so it's always a real app user, never a raw auth.users id
-- with no role/name attached.

ALTER TABLE public.hostel_allotments
    ADD COLUMN IF NOT EXISTS deleted_at timestamptz,
    ADD COLUMN IF NOT EXISTS deleted_by uuid REFERENCES public.users(id);

CREATE INDEX IF NOT EXISTS idx_hostel_allotments_not_deleted
    ON public.hostel_allotments (id) WHERE deleted_at IS NULL;
