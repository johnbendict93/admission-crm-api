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
from pydantic import ValidationError

from app.models.telecallers import TelecallerCreate, TelecallerResponse


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
        body = response.json()
        assert isinstance(body["items"], list)
        assert isinstance(body["total"], int)
        assert body["limit"] == 50
        assert body["offset"] == 0
        assert isinstance(body["has_more"], bool)

    def test_pagination_limit_is_respected(self, client, new_telecaller):
        response = client.get("/telecallers/?limit=1&offset=0")
        assert response.status_code == 200
        body = response.json()
        assert len(body["items"]) <= 1
        assert body["limit"] == 1
        assert body["offset"] == 0

    def test_pagination_total_and_has_more_are_accurate(
        self, client, supabase, telecallers_table
    ):
        # Deterministic regardless of whatever else is on dev: create two
        # known rows, then confirm `total` counts every matching row (not
        # just the page) and `has_more` reflects whether more rows exist
        # beyond the current page - not just that the array got sliced.
        id_a = (
            supabase.table(telecallers_table)
            .insert({"name": "Pytest Pagination Telecaller A"})
            .execute()
        ).data[0]["id"]
        id_b = (
            supabase.table(telecallers_table)
            .insert({"name": "Pytest Pagination Telecaller B"})
            .execute()
        ).data[0]["id"]
        try:
            page = client.get("/telecallers/?limit=1&offset=0")
            assert page.status_code == 200
            body = page.json()
            assert body["total"] >= 2
            assert body["has_more"] is True

            full_limit = min(body["total"], 200)
            full_page = client.get(f"/telecallers/?limit={full_limit}&offset=0")
            assert full_page.status_code == 200
            full_body = full_page.json()
            assert len(full_body["items"]) == full_body["total"]
            assert full_body["has_more"] is False
        finally:
            supabase.table(telecallers_table).delete().eq("id", id_a).execute()
            supabase.table(telecallers_table).delete().eq("id", id_b).execute()


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


class TestBlankEmailRegression:
    """A telecaller row with email = '' (found on dev, Sept 2026) must not
    crash the list/get endpoints - same bug class as leads."""

    @staticmethod
    def _base(email):
        return {
            "id": "00000000-0000-0000-0000-000000000001",
            "name": "Blank Email Test",
            "email": email,
        }

    @pytest.mark.parametrize("blank", ["", " ", "   ", "\t"])
    def test_response_model_turns_blank_email_into_none(self, blank):
        assert TelecallerResponse(**self._base(blank)).email is None

    def test_response_model_keeps_valid_and_missing_email(self):
        assert (
            TelecallerResponse(**self._base("a@example.com")).email
            == "a@example.com"
        )
        assert TelecallerResponse(**self._base(None)).email is None

    def test_response_model_still_rejects_a_malformed_email(self):
        with pytest.raises(ValidationError):
            TelecallerResponse(**self._base("not-an-email"))

    def test_create_model_stays_strict_about_blank_email(self):
        with pytest.raises(ValidationError):
            TelecallerCreate(name="X", email="")

    def test_list_and_get_survive_a_row_with_blank_email(
        self, client, supabase, telecallers_table
    ):
        row = (
            supabase.table(telecallers_table)
            .insert({"name": "Pytest Blank Email Telecaller", "email": ""})
            .execute()
            .data[0]
        )
        try:
            got = client.get(f"/telecallers/{row['id']}")
            assert got.status_code == 200
            assert got.json()["email"] is None
            listed = client.get("/telecallers/?limit=200&offset=0")
            assert listed.status_code == 200
        finally:
            supabase.table(telecallers_table).delete().eq("id", row["id"]).execute()
