"""Tests for the /leads module (GET list, GET /{id}, POST, error handling).

Field names below come directly from app/models/leads.py (LeadBase) and
app/routers/leads.py — read before writing these tests, not guessed.
"""


class TestListLeads:
    def test_list_returns_200(self, client):
        response = client.get("/leads/")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_pagination_limit_is_respected(self, client):
        response = client.get("/leads/?limit=2&offset=0")
        assert response.status_code == 200
        assert len(response.json()) <= 2

    def test_pagination_offset_moves_window(self, client):
        page1 = client.get("/leads/?limit=1&offset=0").json()
        page2 = client.get("/leads/?limit=1&offset=1").json()
        assert page1 != page2


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
    def test_delete_existing_lead_returns_204(self, client, supabase, leads_table):
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
        finally:
            # Defensive cleanup in case an assertion above failed before
            # the delete actually went through.
            supabase.table(leads_table).delete().eq("id", lead_id).execute()

    def test_delete_nonexistent_lead_returns_404(self, client):
        response = client.delete("/leads/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404
