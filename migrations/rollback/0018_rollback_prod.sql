-- ROLLBACK for migration 0018 (prod): removes leads.parent_phone.
-- WARNING: any parent_phone values written after 0018 are lost.
-- Apply to the SAME environment only, then delete the 0018 row from schema_migrations
-- and revert the API code that selects parent_phone (LEAD_COLUMNS, LeadBase/LeadUpdate).

BEGIN;
ALTER TABLE public.leads DROP COLUMN IF EXISTS parent_phone;
COMMIT;
