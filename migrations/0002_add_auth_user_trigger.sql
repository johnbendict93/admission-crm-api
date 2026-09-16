-- Migration 0002: Add missing auth-user-provisioning trigger to dev
--
-- Discovered while diagnosing why the pytest suite's login-based fixtures
-- failed with "no matching row exists in the users table" even after real
-- Supabase Auth accounts were created successfully: dev's auth.users table
-- had NO trigger at all provisioning matching rows in public.users, while
-- production does (trigger on_auth_user_created -> handle_new_auth_user()).
--
-- Root cause: migration 0001 was pg_dump'd with --schema=public, so it only
-- captured handle_new_auth_user() as a function definition - it could not
-- capture the trigger itself, since that trigger lives on auth.users, which
-- is outside the public schema and outside pg_dump's --schema=public scope.
-- 0001 was then STAMPED (not applied) on both dev and prod on the assumption
-- both already matched the dumped state - true for prod, false for dev,
-- which apparently never had this trigger wired up at all.
--
-- Both statements below are copied verbatim from production via
-- pg_get_functiondef()/pg_get_triggerdef() (not retyped/reconstructed), and
-- use CREATE OR REPLACE so this migration is safe to re-run.
--
-- This must be run with `apply`, not `stamp` - unlike 0001, this is a real
-- change dev actually needs:
--     python migrations/run_migrations.py apply --env dev

CREATE OR REPLACE FUNCTION public.handle_new_auth_user()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
AS $function$
BEGIN
  INSERT INTO public.users (id, email, full_name, role, is_active)
  VALUES (
    NEW.id,
    NEW.email,
    COALESCE(NEW.raw_user_meta_data->>'full_name', split_part(NEW.email, '@', 1)),
    'counselor',
    true
  )
  ON CONFLICT (id) DO NOTHING;
  RETURN NEW;
END;
$function$;

CREATE OR REPLACE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW
    EXECUTE FUNCTION handle_new_auth_user();
