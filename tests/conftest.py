"""Shared pytest fixtures for the Admission CRM API test suite.

Everything here reads table names from the same app.core.config.Settings
that the app itself uses (no hardcoded table/URL strings), and uses the
same DI'd Supabase client (app.core.database.get_supabase_client) rather
than constructing a second, separately-configured client.
"""
import os
import sys

import pytest
from fastapi.testclient import TestClient

# Make "app" importable when pytest is run from the project root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings  # noqa: E402
from app.core.database import get_supabase_client  # noqa: E402
from app.main import app  # noqa: E402


def pytest_configure(config):
    """Hard safety gate, evaluated before any test runs (and before most
    fixtures even exist). This suite creates and deletes rows on every
    run, so it must never be able to reach production — not on a wrong
    ENVIRONMENT value in .env, not on a copy-paste mistake in DEV_*.
    """
    if settings.ENVIRONMENT != "development":
        pytest.exit(
            f"Refusing to run: ENVIRONMENT={settings.ENVIRONMENT!r}, not "
            "'development'. This suite must never run against production.",
            returncode=1,
        )
    if settings.SUPABASE_URL == settings.PROD_SUPABASE_URL:
        pytest.exit(
            "Refusing to run: the active SUPABASE_URL matches "
            "PROD_SUPABASE_URL. DEV_SUPABASE_URL is likely misconfigured "
            "to point at production.",
            returncode=1,
        )


def _login(email: str, password: str, role_label: str) -> dict:
    """Logs in via the real /auth/login endpoint (real Supabase Auth call,
    not mocked) and returns the full response body (access_token + user).
    Used to build the session-scoped fixtures below so we only log in once
    per test run per role, not once per test."""
    if not email or not password:
        pytest.exit(
            f"TEST_{role_label.upper()}_EMAIL/PASSWORD not set in .env. Run "
            "scripts/create_test_users.py once against dev, then add the "
            "printed credentials to .env.",
            returncode=1,
        )
    login_client = TestClient(app)
    response = login_client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, f"Test {role_label} login failed: {response.text}"
    return response.json()


@pytest.fixture(scope="session")
def _admin_login():
    return _login(settings.TEST_ADMIN_EMAIL, settings.TEST_ADMIN_PASSWORD, "admin")


@pytest.fixture(scope="session")
def _viewer_login():
    return _login(settings.TEST_VIEWER_EMAIL, settings.TEST_VIEWER_PASSWORD, "viewer")


@pytest.fixture(scope="session")
def admin_access_token(_admin_login):
    """A real Supabase-issued JWT for the dedicated admin-role test
    account (see scripts/create_test_users.py)."""
    return _admin_login["access_token"]


@pytest.fixture(scope="session")
def admin_user_id(_admin_login):
    """The admin test account's own users.id row - for asserting
    soft-delete/audit-trail fields (deleted_by, created_by) come back set
    to the account that actually performed the request."""
    return _admin_login["user"]["id"]


@pytest.fixture(scope="session")
def viewer_access_token(_viewer_login):
    """A real Supabase-issued JWT for the dedicated viewer-role test
    account (see scripts/create_test_users.py)."""
    return _viewer_login["access_token"]


@pytest.fixture(scope="session")
def client(admin_access_token):
    """FastAPI TestClient — talks to the app in-process, over the real
    Supabase connection configured in .env (no mocking of the DB layer).
    Sends a real admin-role JWT by default so every existing CRUD test
    keeps working unchanged (admin passes every role check); auth- and
    role-specific tests (tests/test_auth.py) override/omit the header
    explicitly, and tests that need viewer-role restrictions use the
    separate `viewer_client` fixture below instead."""
    test_client = TestClient(app)
    test_client.headers.update({"Authorization": f"Bearer {admin_access_token}"})
    return test_client


@pytest.fixture(scope="session")
def viewer_client(viewer_access_token):
    """Same as `client`, but authenticated as the viewer-role test
    account — for asserting the read-only restriction (403 on
    POST/PATCH/DELETE, 200 on GET)."""
    test_client = TestClient(app)
    test_client.headers.update({"Authorization": f"Bearer {viewer_access_token}"})
    return test_client


@pytest.fixture(scope="session")
def supabase():
    """The exact same cached Supabase client instance the app's dependency
    injection uses — for test setup/verification/cleanup only, never for
    the assertions themselves (those go through the API)."""
    return get_supabase_client()


@pytest.fixture(scope="session")
def leads_table():
    return settings.LEADS_TABLE


@pytest.fixture(scope="session")
def applicants_table():
    return settings.APPLICANTS_TABLE


@pytest.fixture(scope="session")
def applications_table():
    return settings.APPLICATIONS_TABLE


def count_rows(supabase, table_name: str) -> int:
    response = supabase.table(table_name).select("id").execute()
    return len(response.data)


@pytest.fixture(autouse=True)
def verify_db_untouched(supabase, leads_table, applicants_table, applications_table):
    """Runs around every single test. Whatever a test does — including its
    own try/finally cleanup of any row it created — the three tables must
    have exactly the same row counts after the test as before it. This is
    the automated version of the manual "check row count before/after"
    step done for every prior live verification in this project.
    """
    tables = [leads_table, applicants_table, applications_table]
    before = {t: count_rows(supabase, t) for t in tables}
    yield
    after = {t: count_rows(supabase, t) for t in tables}
    assert after == before, (
        "Row counts changed during test — a test left the database dirty. "
        f"before={before} after={after}"
    )


@pytest.fixture
def existing_lead(supabase, leads_table):
    """A real, pre-existing lead id (never created or deleted by the
    tests) — used for GET /{id} happy-path checks."""
    response = supabase.table(leads_table).select("id").is_("deleted_at", "null").limit(1).execute()
    assert response.data, "No existing leads found — seed data expected in 'leads'"
    return response.data[0]["id"]


@pytest.fixture
def existing_applicant(supabase, applicants_table):
    """A real, pre-existing applicant id — used for GET /{id} checks and
    as the FK target when creating a test application."""
    response = supabase.table(applicants_table).select("id").is_("deleted_at", "null").limit(1).execute()
    assert response.data, "No existing applicants found — seed data expected in 'applicants'"
    return response.data[0]["id"]


@pytest.fixture
def existing_application(supabase, applications_table):
    """A real, pre-existing application id — used for GET /{id) checks."""
    response = supabase.table(applications_table).select("id").is_("deleted_at", "null").limit(1).execute()
    assert response.data, "No existing applications found — seed data expected in 'applications'"
    return response.data[0]["id"]
