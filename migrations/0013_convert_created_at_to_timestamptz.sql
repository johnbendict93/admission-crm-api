-- Migration 0013: Convert created_at to timestamptz on 5 tables
--
-- Fixes a timezone-type inconsistency: leads, telecallers, call_schedules,
-- campus_visits and followups store created_at as `timestamp without time
-- zone`, while every other table in the schema (applicants, applications,
-- fee_payments, scholarships, hostel_allotments, document_types,
-- lookup_values, settings, counseling_sessions) already uses `timestamptz`.
--
-- This is a catalog-only, zero-data-risk conversion because:
--   1. created_at on all 5 tables is DEFAULT now() and never app-written
--      (grepped both this repo and the live Streamlit app, dce_crm -
--      confirmed no insert ever supplies created_at explicitly).
--   2. The DB session timezone was live-verified as UTC before writing
--      this migration (current_setting('TIMEZONE'), pg_settings.source =
--      'configuration file', and a pg_db_role_setting scan across every
--      role/database found zero per-role or per-database TimeZone
--      override - so every connection, including PostgREST's, sees the
--      same UTC default). Postgres's implicit timestamp -> timestamptz
--      cast interprets existing naive values using the session
--      timezone at cast time, which is UTC here - identical to how
--      those values are already being generated and read everywhere
--      else in the app, so this changes zero existing timestamps.
--   3. Live audit immediately before writing this (information_schema.
--      columns + pg_indexes + pg_depend, Sept 2026): no index and no
--      view/rule references created_at on any of the 5 tables, so
--      there's nothing else to update alongside the column type.
--
-- Explicitly OUT OF SCOPE (separate, higher-risk task, not bundled here):
-- call_schedules.scheduled_time, which IS app-written as naive local IST
-- time by both this API and the Streamlit app with no offset. A blind
-- type conversion there would shift every existing scheduled call by
-- 5.5 hours. That needs a data-converting migration plus a code fix in
-- both writers, scoped and verified on its own.
--
-- Cross-app check: grepped dce_crm (the live Streamlit app) for every
-- created_at reference. Only read-paths are .order("created_at") (sort
-- order is unaffected - both types compare by the same underlying UTC
-- instant) and one date-boundary filter, get_today_leads()'s
-- .gte("created_at", str(date.today())), which goes through PostgREST
-- and continues to work identically per point 2 above. No naive-vs-
-- aware Python datetime comparison exists anywhere against these
-- columns. Display code either truncates to date-only or renders the
-- raw string - cosmetic-only impact (an ISO offset suffix appears where
-- none did before).

ALTER TABLE public.leads
    ALTER COLUMN created_at TYPE timestamptz;

ALTER TABLE public.telecallers
    ALTER COLUMN created_at TYPE timestamptz;

ALTER TABLE public.call_schedules
    ALTER COLUMN created_at TYPE timestamptz;

ALTER TABLE public.campus_visits
    ALTER COLUMN created_at TYPE timestamptz;

ALTER TABLE public.followups
    ALTER COLUMN created_at TYPE timestamptz;
