"""Tests for per-user JWT authentication (app/core/jwt_auth.py) and the
POST /auth/login endpoint (app/routers/auth.py), which replace the old
shared API-key dependency. The /health endpoint is intentionally left
open and is not covered here.

These hit real Supabase Auth (via the dedicated test accounts from
scripts/create_test_users.py) — nothing here is mocked.
"""
from app.core.config import settings


class TestLogin:
    def test_login_with_correct_credentials_returns_token(self, client):
        response = client.post(
            "/auth/login",
            json={"email": settings.TEST_ADMIN_EMAIL, "password": settings.TEST_ADMIN_PASSWORD},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["access_token"]
        assert body["token_type"] == "bearer"
        assert body["user"]["email"] == settings.TEST_ADMIN_EMAIL
        assert body["user"]["role"] == "admin"

    def test_login_with_wrong_password_returns_401(self, client):
        response = client.post(
            "/auth/login",
            json={"email": settings.TEST_ADMIN_EMAIL, "password": "definitely-the-wrong-password"},
        )
        assert response.status_code == 401
        assert response.status_code != 500

    def test_login_with_nonexistent_email_returns_401(self, client):
        response = client.post(
            "/auth/login",
            json={"email": "no-such-user@admission-crm-dev.com", "password": "whatever123"},
        )
        assert response.status_code == 401

    def test_login_with_malformed_email_returns_422(self, client):
        response = client.post(
            "/auth/login",
            json={"email": "not-an-email", "password": "whatever123"},
        )
        assert response.status_code == 422


class TestJwtAuth:
    def test_request_without_token_returns_401(self, client):
        response = client.get("/leads/", headers={"Authorization": ""})
        assert response.status_code == 401
        assert response.status_code != 500

    def test_request_with_malformed_header_returns_401(self, client):
        response = client.get("/leads/", headers={"Authorization": "not-a-bearer-token"})
        assert response.status_code == 401

    def test_request_with_garbage_token_returns_401(self, client):
        response = client.get("/leads/", headers={"Authorization": "Bearer garbage.not.a.jwt"})
        assert response.status_code == 401

    def test_request_with_valid_token_succeeds(self, client):
        # The shared `client` fixture already sends a real admin JWT by
        # default (see conftest.py) — this confirms that path works for
        # all three protected routers, not only the ones exercised
        # elsewhere in the suite.
        assert client.get("/leads/").status_code == 200
        assert client.get("/applicants/").status_code == 200
        assert client.get("/applications/").status_code == 200

    def test_health_check_does_not_require_token(self, client):
        response = client.get("/health", headers={"Authorization": ""})
        assert response.status_code == 200


class TestRoleBasedAccess:
    """viewer is read-only; only admin/staff may DELETE (app/core/jwt_auth.py:
    require_writer / require_deleter). The `client` fixture is admin-role,
    `viewer_client` is viewer-role — see conftest.py."""

    def test_viewer_can_read(self, viewer_client):
        assert viewer_client.get("/leads/").status_code == 200
        assert viewer_client.get("/applicants/").status_code == 200
        assert viewer_client.get("/applications/").status_code == 200

    def test_viewer_cannot_create_lead(self, viewer_client):
        response = viewer_client.post(
            "/leads/", json={"name": "Role Test Lead", "phone": "9999999999"}
        )
        assert response.status_code == 403

    def test_viewer_cannot_update_lead(self, viewer_client, existing_lead):
        response = viewer_client.patch(f"/leads/{existing_lead}", json={"status": "Contacted"})
        assert response.status_code == 403

    def test_viewer_cannot_delete_lead(self, viewer_client, existing_lead):
        response = viewer_client.delete(f"/leads/{existing_lead}")
        assert response.status_code == 403

    def test_admin_can_delete(self, client, supabase, leads_table):
        # Prove the flip side of the viewer restriction: admin's DELETE
        # actually reaches the service layer (create-then-delete so the
        # DB-untouched fixture still balances). DELETE is now a soft
        # delete (see migrations/0003_add_soft_delete_columns.sql) — the
        # row survives with deleted_at set, so it still needs an explicit
        # hard-delete cleanup here, unlike when DELETE itself removed it.
        created = (
            supabase.table(leads_table)
            .insert({"name": "Role Test Delete", "phone": "8888888888"})
            .execute()
        )
        lead_id = created.data[0]["id"]
        try:
            response = client.delete(f"/leads/{lead_id}")
            assert response.status_code == 204
        finally:
            supabase.table(leads_table).delete().eq("id", lead_id).execute()
