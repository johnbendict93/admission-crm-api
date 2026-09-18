"""Tests for the /applicants module (GET list, GET /{id}, POST, error
handling). Field names come directly from app/models/applicants.py
(ApplicantBase) and app/routers/applicants.py.
"""


class TestListApplicants:
    def test_list_returns_200(self, client):
        response = client.get("/applicants/")
        assert response.status_code == 200
        body = response.json()
        assert isinstance(body["items"], list)
        assert isinstance(body["total"], int)
        assert body["limit"] == 50
        assert body["offset"] == 0
        assert isinstance(body["has_more"], bool)

    def test_pagination_limit_is_respected(self, client):
        response = client.get("/applicants/?limit=3&offset=0")
        assert response.status_code == 200
        body = response.json()
        assert len(body["items"]) <= 3
        assert body["limit"] == 3
        assert body["offset"] == 0

    def test_pagination_offset_moves_window(self, client):
        page1 = client.get("/applicants/?limit=1&offset=0").json()
        page2 = client.get("/applicants/?limit=1&offset=1").json()
        assert page1["items"] != page2["items"]

    def test_pagination_total_and_has_more_are_accurate(
        self, client, supabase, applicants_table
    ):
        # Deterministic regardless of whatever else is on dev: create two
        # known rows, then confirm `total` counts every matching row (not
        # just the page) and `has_more` reflects whether more rows exist
        # beyond the current page - not just that the array got sliced.
        id_a = (
            supabase.table(applicants_table)
            .insert({"first_name": "Pytest", "last_name": "PaginationA", "phone": "9999900202"})
            .execute()
        ).data[0]["id"]
        id_b = (
            supabase.table(applicants_table)
            .insert({"first_name": "Pytest", "last_name": "PaginationB", "phone": "9999900203"})
            .execute()
        ).data[0]["id"]
        try:
            page = client.get("/applicants/?limit=1&offset=0")
            assert page.status_code == 200
            body = page.json()
            assert body["total"] >= 2
            assert body["has_more"] is True

            full_limit = min(body["total"], 200)
            full_page = client.get(f"/applicants/?limit={full_limit}&offset=0")
            assert full_page.status_code == 200
            full_body = full_page.json()
            assert len(full_body["items"]) == full_body["total"]
            assert full_body["has_more"] is False
        finally:
            supabase.table(applicants_table).delete().eq("id", id_a).execute()
            supabase.table(applicants_table).delete().eq("id", id_b).execute()


class TestGetApplicant:
    def test_get_existing_applicant_returns_200(self, client, existing_applicant):
        response = client.get(f"/applicants/{existing_applicant}")
        assert response.status_code == 200
        assert response.json()["id"] == existing_applicant

    def test_get_nonexistent_applicant_returns_404(self, client):
        response = client.get("/applicants/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404


class TestCreateApplicant:
    def test_create_applicant_then_delete(self, client, supabase, applicants_table, admin_user_id):
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
            # created_by is set server-side from the authenticated caller
            # (app/services/applicants_service.create_applicant), never
            # from the request body — the payload above deliberately
            # doesn't send one, so this proves the server-side wiring.
            assert body["created_by"] == admin_user_id
        finally:
            if created_id:
                supabase.table(applicants_table).delete().eq("id", created_id).execute()

    def test_create_applicant_ignores_client_supplied_created_by(
        self, client, supabase, applicants_table, admin_user_id
    ):
        # A client-supplied created_by must never be trusted — it always
        # gets overwritten with the authenticated caller's own id.
        payload = {
            "first_name": "Pytest",
            "last_name": "SpoofedCreator",
            "phone": "9998887771",
            "created_by": "00000000-0000-0000-0000-000000000000",
        }
        created_id = None
        try:
            response = client.post("/applicants/", json=payload)
            assert response.status_code == 201
            body = response.json()
            created_id = body["id"]
            assert body["created_by"] == admin_user_id
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
    def test_delete_existing_applicant_returns_204(
        self, client, supabase, applicants_table, admin_user_id
    ):
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

            # Soft delete, not hard delete — same check as leads.
            row = (
                supabase.table(applicants_table)
                .select("id,deleted_at,deleted_by")
                .eq("id", applicant_id)
                .single()
                .execute()
            ).data
            assert row is not None, "row was hard-deleted, not soft-deleted"
            assert row["deleted_at"] is not None
            assert row["deleted_by"] == admin_user_id
        finally:
            supabase.table(applicants_table).delete().eq("id", applicant_id).execute()

    def test_delete_nonexistent_applicant_returns_404(self, client):
        response = client.delete("/applicants/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404

    def test_delete_already_deleted_applicant_returns_404(self, client, supabase, applicants_table):
        insert_response = (
            supabase.table(applicants_table)
            .insert({"first_name": "Pytest", "last_name": "DoubleDelete", "phone": "9999900007"})
            .execute()
        )
        applicant_id = insert_response.data[0]["id"]
        try:
            first = client.delete(f"/applicants/{applicant_id}")
            assert first.status_code == 204
            second = client.delete(f"/applicants/{applicant_id}")
            assert second.status_code == 404
        finally:
            supabase.table(applicants_table).delete().eq("id", applicant_id).execute()
