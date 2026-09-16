-- Migration 0003: Soft-delete + minimal audit-trail columns
--
-- Adds deleted_at/deleted_by to leads, applicants and applications so
-- DELETE becomes a soft delete (row stays, gets marked) instead of a hard
-- delete. deleted_by references public.users(id) - the same table
-- auth-provisioned users land in (see migration 0002) - so it's always a
-- real app user, never a raw auth.users id with no role/name attached.
--
-- Partial indexes on deleted_at IS NULL speed up the new default filter
-- every GET list/detail query now applies (WHERE deleted_at IS NULL),
-- without wasting index space on rows that are already soft-deleted.
--
-- Live-audited immediately before writing this (information_schema.columns
-- on dev, Sept 2026): confirmed leads/applicants/applications match the
-- service-layer column lists exactly, and none of the three already had
-- deleted_at/deleted_by under any name.

ALTER TABLE public.leads
    ADD COLUMN IF NOT EXISTS deleted_at timestamptz,
    ADD COLUMN IF NOT EXISTS deleted_by uuid REFERENCES public.users(id);

ALTER TABLE public.applicants
    ADD COLUMN IF NOT EXISTS deleted_at timestamptz,
    ADD COLUMN IF NOT EXISTS deleted_by uuid REFERENCES public.users(id);

ALTER TABLE public.applications
    ADD COLUMN IF NOT EXISTS deleted_at timestamptz,
    ADD COLUMN IF NOT EXISTS deleted_by uuid REFERENCES public.users(id);

CREATE INDEX IF NOT EXISTS idx_leads_not_deleted
    ON public.leads (id) WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_applicants_not_deleted
    ON public.applicants (id) WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_applications_not_deleted
    ON public.applications (id) WHERE deleted_at IS NULL;
