-- ROLLBACK for migration 0019 (dev): drops fee_due_schedule entirely.
-- WARNING: any rows written since 0019 was applied are lost.
-- Apply to the SAME environment only, then delete the 0019 row from
-- schema_migrations and revert any API code that reads/writes this table.

BEGIN;
DROP TABLE IF EXISTS public.fee_due_schedule;
COMMIT;
