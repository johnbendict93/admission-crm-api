"""Tests for the /telecallers module (GET list, GET /{id}, POST, PATCH,
DELETE, soft-delete verification). Field names come directly from
app/models/telecallers.py (TelecallerBase) and
app/routers/telecallers.py.

Like fee_payments/scholarships/hostel_allotments, telecallers has zero
pre-existing seed rows on dev (confirmed live, Sept 2026, before writing
this module) - so there's no "existing_telecaller" fixture pulling a row
that's always there. Every test that needs one creates and cleans up its
own instead, same pattern as tests/test_hostel_allotments.py. Also,
unlike every prior module, telecallers has no FK to another table, so
fixtures here need no existing_applicant-style dependency.
"""
import pytest


@pytest.fixture
def new_telecaller(supabase, telecallers_table):
    """Creates one telecaller row directly (bypassing the API, same as
    existing_lead/applicant/application do for setup), yields its id, and
    hard-deletes it afterward. Exists because this table has no
    pre-existing seed data to borrow."""
    insert_response = (
        supabase.table(telecallers_table)
        .insert({"name": "Priya Test Telecaller"})
        .execute()
    )
    telecaller_id = insert_response.data[0]["id"]
    yield telecaller_id
    supabase.table(telecallers_table).delete().eq("id", telecaller_id).execute()


class TestListTelecallers:
    def test_list_returns_200(self, client, new_telecaller):
        response = client.get("/telecallers/")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_pagination_limit_is_respected(self, client, new_telecaller):
        response = client.get("/telecallers/?limit=1&offset=0")
        assert response.status_code == 200
        assert len(response.json()) <= 1


class TestGetTelecaller:
    def test_get_existing_telecaller_returns_200(self, client, new_telecaller):
        response = client.get(f"/telecallers/{new_telecaller}")
        assert response.status_code == 200
        assert response.json()["id"] == new_telecaller

    def test_get_nonexistent_telecaller_returns_404(self, client):
        response = client.get("/telecallers/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404


class TestCreateTelecaller:
    def test_create_telecaller_then_delete(self, client, supabase, telecallers_table):
        payload = {
            "name": "Kavya New Telecaller",
            "email": "kavya.telecaller@example.com",
            "phone": "9876543210",
            "department": "Admissions",
        }
        created_id = None
        try:
            response = client.post("/telecallers/", json=payload)
            assert response.status_code == 201
            body = response.json()
            created_id = body["id"]
            assert body["name"] == payload["name"]
            assert body["email"] == payload["email"]
            assert body["phone"] == payload["phone"]
            assert body["department"] == payload["department"]
            # DB default applies when the request omits this.
            assert body["active"] is True
        finally:
            if created_id:
                supabase.table(telecallers_table).delete().eq("id", created_id).execute()


class TestUpdateTelecaller:
    def test_update_existing_telecaller_returns_200(self, client, new_telecaller):
        response = client.patch(
            f"/telecallers/{new_telecaller}", json={"active": False}
        )
        assert response.status_code == 200
        assert response.json()["active"] is False
        assert response.json()["id"] == new_telecaller

    def test_update_nonexistent_telecaller_returns_404(self, client):
        response = client.patch(
            "/telecallers/00000000-0000-0000-0000-000000000000",
            json={"active": False},
        )
        assert response.status_code == 404


class TestDeleteTelecaller:
    def test_delete_existing_telecaller_returns_204(
        self, client, supabase, telecallers_table, admin_user_id
    ):
        insert_response = (
            supabase.table(telecallers_table)
            .insert({"name": "Delete-Test Telecaller"})
            .execute()
        )
        telecaller_id = insert_response.data[0]["id"]
        try:
            response = client.delete(f"/telecallers/{telecaller_id}")
            assert response.status_code == 204
            follow_up = client.get(f"/telecallers/{telecaller_id}")
            assert follow_up.status_code == 404

            # Soft delete, not hard delete — same check as every other module.
            row = (
                supabase.table(telecallers_table)
                .select("id,deleted_at,deleted_by")
                .eq("id", telecaller_id)
                .single()
                .execute()
            ).data
            assert row is not None, "row was hard-deleted, not soft-deleted"
            assert row["deleted_at"] is not None
            assert row["deleted_by"] == admin_user_id
        finally:
            supabase.table(telecallers_table).delete().eq("id", telecaller_id).execute()

    def test_delete_nonexistent_telecaller_returns_404(self, client):
        response = client.delete("/telecallers/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404

    def test_delete_already_deleted_telecaller_returns_404(
        self, client, supabase, telecallers_table
    ):
        insert_response = (
            supabase.table(telecallers_table)
            .insert({"name": "Double-Delete Telecaller"})
            .execute()
        )
        telecaller_id = insert_response.data[0]["id"]
        try:
            first = client.delete(f"/telecallers/{telecaller_id}")
            assert first.status_code == 204
            second = client.delete(f"/telecallers/{telecaller_id}")
            assert second.status_code == 404
        finally:
            supabase.table(telecallers_table).delete().eq("id", telecaller_id).execute()
