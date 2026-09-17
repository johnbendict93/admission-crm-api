-- Migration 0011: Attach the shared updated_at trigger to settings
--
-- settings already has an updated_at column (confirmed live via
-- information_schema.columns, Sept 2026), but unlike every other
-- updated_at-bearing table in this schema (fee_payments,
-- hostel_allotments, scholarships, applicants, applications), it has no
-- trigger keeping that column current on UPDATE (confirmed live via
-- pg_trigger - empty). This attaches the same shared
-- public.update_updated_at() function those tables already use (defined
-- in prod_schema.sql, not created here) rather than having the app
-- layer set updated_at manually, keeping this table consistent with the
-- established convention (checked fee_payments_service.py: it never
-- sets updated_at itself, relying entirely on its DB trigger).
--
-- This is unrelated to the delete-strategy decision for this module
-- (settings uses is_active, like document_types/lookup_values - see the
-- module's own service file) - this migration only fixes a
-- pre-existing gap in updated_at maintenance found while auditing the
-- table before building against it.

CREATE TRIGGER settings_updated_at
    BEFORE UPDATE ON public.settings
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();
