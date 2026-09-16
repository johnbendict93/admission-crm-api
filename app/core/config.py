from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Which credential set below is actually used — switch environments by
    # changing this one value (e.g. via a real ENVIRONMENT env var in a
    # deployment platform), never by hand-editing a URL/key.
    ENVIRONMENT: Literal["development", "production"] = "production"

    # Both credential sets live side by side in .env (gitignored, never
    # committed). DEV_* defaults to "" so this doesn't break before the dev
    # Supabase project exists yet — ENVIRONMENT stays "production" until
    # DEV_* is actually populated and ENVIRONMENT is flipped.
    DEV_SUPABASE_URL: str = ""
    DEV_SUPABASE_KEY: str = ""
    PROD_SUPABASE_URL: str
    PROD_SUPABASE_KEY: str

    # anon (public) keys - safe to be non-secret, unlike SUPABASE_KEY above
    # (which is the service_role key). Used ONLY for the login endpoint's
    # sign_in_with_password() call (see app/routers/auth.py) - the correct,
    # minimal-privilege key for a client-facing auth call, as opposed to the
    # service_role key the rest of the app uses for ordinary CRUD.
    DEV_SUPABASE_ANON_KEY: str = ""
    PROD_SUPABASE_ANON_KEY: str = ""

    # Direct Postgres connection strings (Supabase dashboard -> Connect ->
    # Connection string -> URI), used ONLY by migrations/run_migrations.py.
    # DDL (CREATE TABLE/ALTER TABLE/etc.) can't go through PostgREST, so the
    # migration runner needs a direct connection distinct from SUPABASE_URL/
    # SUPABASE_KEY above, which the app itself uses for ordinary CRUD. Both
    # default to "" so the app can still boot without them; only the
    # migration runner requires whichever one it's pointed at.
    DEV_DATABASE_URL: str = ""
    PROD_DATABASE_URL: str = ""

    TEST_ADMIN_EMAIL: str = ""
    TEST_ADMIN_PASSWORD: str = ""
    TEST_VIEWER_EMAIL: str = ""
    TEST_VIEWER_PASSWORD: str = ""
    GROQ_API_KEY: str = ""
    COLLEGE_SHORT: str = "DCE"

    # Comma-separated list; e.g. "http://localhost:3000,https://your-app.vercel.app"
    ALLOWED_ORIGINS: str = "http://localhost:3000"
    LEADS_TABLE: str = "leads"
    APPLICANTS_TABLE: str = "applicants"
    APPLICATIONS_TABLE: str = "applications"
    FEE_PAYMENTS_TABLE: str = "fee_payments"
    SCHOLARSHIPS_TABLE: str = "scholarships"
    HOSTEL_ALLOTMENTS_TABLE: str = "hostel_allotments"
    TELECALLERS_TABLE: str = "telecallers"
    USERS_TABLE: str = "users"

    @property
    def SUPABASE_URL(self) -> str:
        return self.PROD_SUPABASE_URL if self.ENVIRONMENT == "production" else self.DEV_SUPABASE_URL

    @property
    def SUPABASE_KEY(self) -> str:
        return self.PROD_SUPABASE_KEY if self.ENVIRONMENT == "production" else self.DEV_SUPABASE_KEY

    @property
    def SUPABASE_ANON_KEY(self) -> str:
        return self.PROD_SUPABASE_ANON_KEY if self.ENVIRONMENT == "production" else self.DEV_SUPABASE_ANON_KEY

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    class Config:
        env_file = ".env"


settings = Settings()
