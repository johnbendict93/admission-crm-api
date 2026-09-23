-- ROLLBACK for migration 0020 (dev): drops enquiry_monthly_history entirely.
-- WARNING: any rows written since 0020 was applied are lost.
-- Apply to the SAME environment only, then delete the 0020 row from
-- schema_migrations and revert any API code that reads/writes this table.

BEGIN;
DROP TABLE IF EXISTS public.enquiry_monthly_history;
COMMIT;
