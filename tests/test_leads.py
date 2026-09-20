"""Tests for the /leads module (GET list, GET /{id}, POST, error handling).

Field names below come directly from app/models/leads.py (LeadBase) and
app/routers/leads.py — read before writing these tests, not guessed.
"""

import pytest
from pydantic import ValidationError

from app.models.leads import LeadCreate, LeadResponse


class TestListLeads:
    def test_list_returns_200(self, client):
        response = client.get("/leads/")
        assert response.status_code == 200
        body = response.json()
        assert isinstance(body["items"], list)
        assert isinstance(body["total"], int)
        assert body["limit"] == 50
        assert body["offset"] == 0
        assert isinstance(body["has_more"], bool)

    def test_pagination_limit_is_respected(self, client):
        response = client.get("/leads/?limit=2&offset=0")
        assert response.status_code == 200
        body = response.json()
        assert len(body["items"]) <= 2
        assert body["limit"] == 2
        assert body["offset"] == 0

    def test_pagination_offset_moves_window(self, client):
        page1 = client.get("/leads/?limit=1&offset=0").json()
        page2 = client.get("/leads/?limit=1&offset=1").json()
        assert page1["items"] != page2["items"]

    def test_pagination_total_and_has_more_are_accurate(
        self, client, supabase, leads_table
    ):
        # Deterministic regardless of whatever else is on dev: create two
        # known rows, then confirm `total` counts every matching row (not
        # just the page) and `has_more` reflects whether more rows exist
        # beyond the current page - not just that the array got sliced.
        id_a = (
            supabase.table(leads_table)
            .insert({"name": "Pytest Pagination A", "phone": "9999900200"})
            .execute()
        ).data[0]["id"]
        id_b = (
            supabase.table(leads_table)
            .insert({"name": "Pytest Pagination B", "phone": "9999900201"})
            .execute()
        ).data[0]["id"]
        try:
            page = client.get("/leads/?limit=1&offset=0")
            assert page.status_code == 200
            body = page.json()
            assert body["total"] >= 2
            assert body["has_more"] is True

            full_limit = min(body["total"], 200)
            full_page = client.get(f"/leads/?limit={full_limit}&offset=0")
            assert full_page.status_code == 200
            full_body = full_page.json()
            assert len(full_body["items"]) == full_body["total"]
            assert full_body["has_more"] is False
        finally:
            supabase.table(leads_table).delete().eq("id", id_a).execute()
            supabase.table(leads_table).delete().eq("id", id_b).execute()


class TestGetLead:
    def test_get_existing_lead_returns_200(self, client, existing_lead):
        response = client.get(f"/leads/{existing_lead}")
        assert response.status_code == 200
        assert response.json()["id"] == existing_lead

    def test_get_nonexistent_lead_returns_404(self, client):
        response = client.get("/leads/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404


class TestCreateLead:
    def test_create_lead_then_delete(self, client, supabase, leads_table):
        payload = {
            "name": "Pytest Test Lead",
            "phone": "9999999999",
            "email": "pytest.lead@example.com",
            "school": "Pytest HSS",
            "parent_phone": "9888888888",
            "status": "New",
        }
        created_id = None
        try:
            response = client.post("/leads/", json=payload)
            assert response.status_code == 201
            body = response.json()
            created_id = body["id"]
            assert body["name"] == payload["name"]
            assert body["phone"] == payload["phone"]
            assert body["email"] == payload["email"]
            assert body["school"] == payload["school"]
            assert body["parent_phone"] == payload["parent_phone"]
            assert body["status"] == payload["status"]
            assert "id" in body and "created_at" in body
        finally:
            if created_id:
                supabase.table(leads_table).delete().eq("id", created_id).execute()


class TestLeadErrorHandling:
    def test_missing_required_fields_returns_handled_error(self, client):
        # "name" and "phone" are required on LeadCreate. Omitting both must
        # surface as a handled 422 (FastAPI request validation), never a
        # raw 500 — and must not create a row.
        response = client.post("/leads/", json={"email": "no-name@example.com"})
        assert response.status_code == 422
        assert response.status_code != 500


class TestUpdateLead:
    def test_update_existing_lead_returns_200(self, client, supabase, leads_table):
        insert_response = (
            supabase.table(leads_table)
            .insert({"name": "Pytest Update Lead", "phone": "9999900001", "status": "New"})
            .execute()
        )
        lead_id = insert_response.data[0]["id"]
        try:
            response = client.patch(f"/leads/{lead_id}", json={"status": "Contacted"})
            assert response.status_code == 200
            assert response.json()["status"] == "Contacted"
            assert response.json()["id"] == lead_id
        finally:
            supabase.table(leads_table).delete().eq("id", lead_id).execute()

    def test_update_nonexistent_lead_returns_404(self, client):
        response = client.patch(
            "/leads/00000000-0000-0000-0000-000000000000", json={"status": "Contacted"}
        )
        assert response.status_code == 404

    def test_update_with_empty_body_returns_400(self, client):
        # Empty payload is an invalid partial update — nothing to apply —
        # and must be rejected before any database call, not with a 500.
        response = client.patch("/leads/00000000-0000-0000-0000-000000000000", json={})
        assert response.status_code == 400
        assert response.status_code != 500


class TestDeleteLead:
    def test_delete_existing_lead_returns_204(self, client, supabase, leads_table, admin_user_id):
        insert_response = (
            supabase.table(leads_table)
            .insert({"name": "Pytest Delete Lead", "phone": "9999900002", "status": "New"})
            .execute()
        )
        lead_id = insert_response.data[0]["id"]
        try:
            response = client.delete(f"/leads/{lead_id}")
            assert response.status_code == 204
            follow_up = client.get(f"/leads/{lead_id}")
            assert follow_up.status_code == 404

            # Soft delete, not hard delete: the row must still physically
            # exist (with deleted_at/deleted_by set), even though the API
            # now treats it as gone. select() bypasses the API's own
            # deleted_at filter, so this can see the row the GET above
            # correctly could not.
            row = (
                supabase.table(leads_table)
                .select("id,deleted_at,deleted_by")
                .eq("id", lead_id)
                .single()
                .execute()
            ).data
            assert row is not None, "row was hard-deleted, not soft-deleted"
            assert row["deleted_at"] is not None
            assert row["deleted_by"] == admin_user_id
        finally:
            # Defensive cleanup in case an assertion above failed before
            # the delete actually went through — hard-deletes regardless
            # of deleted_at, so this always fully removes the test row.
            supabase.table(leads_table).delete().eq("id", lead_id).execute()

    def test_delete_nonexistent_lead_returns_404(self, client):
        response = client.delete("/leads/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404

    def test_delete_already_deleted_lead_returns_404(self, client, supabase, leads_table):
        # Soft delete must not be re-appliable: once deleted_at is set, a
        # second DELETE on the same id has nothing left to match (the
        # service's .is_("deleted_at", "null") guard) and must 404, not
        # silently "succeed" again.
        insert_response = (
            supabase.table(leads_table)
            .insert({"name": "Pytest Double Delete Lead", "phone": "9999900006", "status": "New"})
            .execute()
        )
        lead_id = insert_response.data[0]["id"]
        try:
            first = client.delete(f"/leads/{lead_id}")
            assert first.status_code == 204
            second = client.delete(f"/leads/{lead_id}")
            assert second.status_code == 404
        finally:
            supabase.table(leads_table).delete().eq("id", lead_id).execute()


class TestBlankEmailRegression:
    """Regression for the Sept 2026 outage: two dev rows held email = ''
    (the Streamlit form saves an empty box as an empty string). The strict
    EmailStr on LeadResponse rejected them while serializing GET /leads/,
    so ONE bad row returned a 500 for the whole list.

    Fix (commit 7aff751): LeadResponse turns a blank/whitespace email into
    None on the way OUT. Create/update models stay strict on purpose."""

    def _base(self):
        return {"id": "00000000-0000-0000-0000-000000000001", "name": "A", "phone": "5000000000"}

    @pytest.mark.parametrize("blank", ["", " ", "   ", "\t"])
    def test_response_model_turns_blank_email_into_none(self, blank):
        assert LeadResponse(**self._base(), email=blank).email is None

    def test_response_model_keeps_valid_email_and_missing_email(self):
        assert LeadResponse(**self._base(), email="a@example.com").email == "a@example.com"
        assert LeadResponse(**self._base()).email is None

    def test_response_model_still_rejects_a_malformed_email(self):
        with pytest.raises(ValidationError):
            LeadResponse(**self._base(), email="not-an-email")

    def test_create_model_stays_strict_about_blank_email(self):
        with pytest.raises(ValidationError):
            LeadCreate(name="A", phone="5000000000", email="")

    def test_list_and_get_survive_a_row_with_blank_email(self, client, supabase, leads_table):
        lead_id = (
            supabase.table(leads_table)
            .insert({"name": "Pytest Blank Email", "phone": "5000000999", "email": ""})
            .execute()
        ).data[0]["id"]
        try:
            single = client.get(f"/leads/{lead_id}")
            assert single.status_code == 200
            assert single.json()["email"] is None
            listing = client.get("/leads/?limit=200&offset=0")
            assert listing.status_code == 200
        finally:
            supabase.table(leads_table).delete().eq("id", lead_id).execute()

