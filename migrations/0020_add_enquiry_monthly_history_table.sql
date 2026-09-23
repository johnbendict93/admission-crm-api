-- Migration 0020: add enquiry_monthly_history table
--
-- WHY
--   Module 20 (Time Series Demand Forecaster, ML roadmap) needs a multi-
--   year enquiry trend to learn seasonality + growth from. leads.created_at
--   only spans the current admissions cycle (~1 year) - there is no real
--   multi-year history yet, because this is a brand-new CRM with no real
--   customer usage. John decided (2026-09-23) to backfill a LIGHTWEIGHT
--   synthetic monthly-count history instead of generating full fake `leads`
--   rows for every past year - faster to build, doesn't multiply the
--   leads table, and is honestly framed as illustrative: any real customer
--   starts from day one too and this is exactly the kind of bootstrap data
--   a new install would need until real history accumulates.
--
-- SHAPE
--   One row per (year, month) with a plain enquiry_count - not per-lead
--   detail. `source` records whether a row is synthetic seed history or
--   (once real customers exist) a real monthly aggregate, so nobody
--   mistakes one for the other later. Soft-delete columns match every
--   other table in this repo (migrations 0003-0012, 0019).
--
-- SAFETY (cross-app check done before writing this)
--   * Brand new table - nothing existing references it, so nothing existing
--     can break.
--   * dce_crm (Streamlit) has no code path that touches this table;
--     unaffected.
--   * RLS enabled with NO policy, same reasoning as migration 0019's
--     fee_due_schedule: migration 0015's default-privileges change already
--     means a new table gets zero anon/authenticated grants automatically,
--     and the API's service_role key bypasses RLS as usual.
--   * Apply to DEV first, verify, then PROD. Apply before deploying any API
--     code that reads/writes this table.
--
-- ROLLBACK: migrations/rollback/0020_rollback_dev.sql / 0020_rollback_prod.sql
--   (drops the table; loses any rows written since).

CREATE TABLE public.enquiry_monthly_history (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    year integer NOT NULL,
    month integer NOT NULL CHECK (month BETWEEN 1 AND 12),
    enquiry_count integer NOT NULL CHECK (enquiry_count >= 0),
    source text NOT NULL DEFAULT 'synthetic',
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now(),
    deleted_at timestamptz,
    deleted_by uuid REFERENCES public.users(id),
    UNIQUE (year, month)
);

CREATE TRIGGER enquiry_monthly_history_updated_at
    BEFORE UPDATE ON public.enquiry_monthly_history
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();

ALTER TABLE public.enquiry_monthly_history ENABLE ROW LEVEL SECURITY;
-- Deliberately no policy: service_role (the API) bypasses RLS; everyone
-- else already has zero table privileges via 0015's default-privileges
-- change, so there is nothing for a policy to grant back.
