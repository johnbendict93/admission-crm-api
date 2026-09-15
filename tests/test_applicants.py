"""Tests for the /applicants module (GET list, GET /{id}, POST, error
handling). Field names come directly from app/models/applicants.py
(ApplicantBase) and app/routers/applicants.py.
"""


class TestListApplicants:
    def test_list_returns_200(self, client):
        response = client.get("/applicants/")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_pagination_limit_is_respected(self, client):
        response = client.get("/applicants/?limit=3&offset=0")
        assert response.status_code == 200
        assert len(response.json()) <= 3

    def test_pagination_offset_moves_window(self, client):
        page1 = client.get("/applicants/?limit=1&offset=0").json()
        page2 = client.get("/applicants/?limit=1&offset=1").json()
        assert page1 != page2


class TestGetApplicant:
    def test_get_existing_applicant_returns_200(self, client, existing_applicant):
        response = client.get(f"/applicants/{existing_applicant}")
        assert response.status_code == 200
        assert response.json()["id"] == existing_applicant

    def test_get_nonexistent_applicant_returns_404(self, client):
        response = client.get("/applicants/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404


class TestCreateApplicant:
    def test_create_applicant_then_delete(self, client, supabase, applicants_table):
        payload = {
            "first_name": "Pytest",
            "last_name": "Applicant",
            "phone": "9998887770",
            "email": "pytest.applicant@example.com",
            "category": "OC",
        }
        created_id = None
        try:
            response = client.post("/applicants/", json=payload)
            assert response.status_code == 201
            body = response.json()
            created_id = body["id"]
            assert body["first_name"] == payload["first_name"]
            assert body["last_name"] == payload["last_name"]
            assert body["phone"] == payload["phone"]
            assert body["email"] == payload["email"]
            assert body["category"] == payload["category"]
            # reg_number is trigger-generated server-side (see set_reg_number
            # trigger audited earlier), never supplied by the client.
            assert body["reg_number"] is not None
        finally:
            if created_id:
                supabase.table(applicants_table).delete().eq("id", created_id).execute()


class TestApplicantErrorHandling:
    def test_invalid_priority_returns_handled_error(self, client):
        # applicants_priority_check restricts priority to High/Normal/Low.
        # Violating it must surface as a handled 400 (via the Supabase
        # APIError -> HTTPException path), never a raw 500, and must not
        # create a row.
        payload = {
            "first_name": "Bad",
            "last_name": "Priority",
            "phone": "9000000000",
            "priority": "Nonexistent",
        }
        response = client.post("/applicants/", json=payload)
        assert response.status_code == 400
        assert response.status_code != 500


class TestUpdateApplicant:
    def test_update_existing_applicant_returns_200(self, client, supabase, applicants_table):
        insert_response = (
            supabase.table(applicants_table)
            .insert({"first_name": "Pytest", "last_name": "UpdateTarget", "phone": "9999900003"})
            .execute()
        )
        applicant_id = insert_response.data[0]["id"]
        try:
            response = client.patch(f"/applicants/{applicant_id}", json={"city": "Chennai"})
            assert response.status_code == 200
            assert response.json()["city"] == "Chennai"
            assert response.json()["id"] == applicant_id
        finally:
            supabase.table(applicants_table).delete().eq("id", applicant_id).execute()

    def test_update_nonexistent_applicant_returns_404(self, client):
        response = client.patch(
            "/applicants/00000000-0000-0000-0000-000000000000", json={"city": "Chennai"}
        )
        assert response.status_code == 404

    def test_update_with_invalid_priority_returns_400(self, client, supabase, applicants_table):
        # applicants_priority_check restricts priority to High/Normal/Low —
        # violating it via PATCH must be a handled 400, not a raw 500, and
        # must not silently apply.
        insert_response = (
            supabase.table(applicants_table)
            .insert({"first_name": "Pytest", "last_name": "BadPatch", "phone": "9999900004"})
            .execute()
        )
        applicant_id = insert_response.data[0]["id"]
        try:
            response = client.patch(
                f"/applicants/{applicant_id}", json={"priority": "Nonexistent"}
            )
            assert response.status_code == 400
            assert response.status_code != 500
        finally:
            supabase.table(applicants_table).delete().eq("id", applicant_id).execute()


class TestDeleteApplicant:
    def test_delete_existing_applicant_returns_204(self, client, supabase, applicants_table):
        insert_response = (
            supabase.table(applicants_table)
            .insert({"first_name": "Pytest", "last_name": "DeleteTarget", "phone": "9999900005"})
            .execute()
        )
        applicant_id = insert_response.data[0]["id"]
        try:
            response = client.delete(f"/applicants/{applicant_id}")
            assert response.status_code == 204
            follow_up = client.get(f"/applicants/{applicant_id}")
            assert follow_up.status_code == 404
        finally:
            supabase.table(applicants_table).delete().eq("id", applicant_id).execute()

    def test_delete_nonexistent_applicant_returns_404(self, client):
        response = client.delete("/applicants/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404
