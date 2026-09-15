"""Tests for the /applications module (GET list, GET /{id}, POST, error
handling). Field names come directly from app/models/applications.py
(ApplicationBase) and app/routers/applications.py.
"""


class TestListApplications:
    def test_list_returns_200(self, client):
        response = client.get("/applications/")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_pagination_limit_is_respected(self, client):
        response = client.get("/applications/?limit=3&offset=0")
        assert response.status_code == 200
        assert len(response.json()) <= 3

    def test_pagination_offset_moves_window(self, client):
        page1 = client.get("/applications/?limit=1&offset=0").json()
        page2 = client.get("/applications/?limit=1&offset=1").json()
        assert page1 != page2


class TestGetApplication:
    def test_get_existing_application_returns_200(self, client, existing_application):
        response = client.get(f"/applications/{existing_application}")
        assert response.status_code == 200
        assert response.json()["id"] == existing_application

    def test_get_nonexistent_application_returns_404(self, client):
        response = client.get("/applications/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404


class TestCreateApplication:
    def test_create_application_then_delete(
        self, client, supabase, applications_table, existing_applicant
    ):
        payload = {
            "applicant_id": existing_applicant,
            "programme": "B.Tech",
            "department": "Pytest Dept",
        }
        created_id = None
        try:
            response = client.post("/applications/", json=payload)
            assert response.status_code == 201
            body = response.json()
            created_id = body["id"]
            assert body["applicant_id"] == payload["applicant_id"]
            assert body["programme"] == payload["programme"]
            assert body["department"] == payload["department"]
            # application_no is trigger-generated server-side (see
            # generate_application_no trigger audited earlier).
            assert body["application_no"] is not None
        finally:
            if created_id:
                supabase.table(applications_table).delete().eq("id", created_id).execute()


class TestApplicationErrorHandling:
    def test_invalid_programme_returns_handled_error(self, client, existing_applicant):
        # applications_programme_check restricts programme to a fixed set
        # of values. Violating it must surface as a handled 400, never a
        # raw 500, and must not create a row.
        payload = {
            "applicant_id": existing_applicant,
            "programme": "Not-A-Real-Programme",
            "department": "Pytest Dept",
        }
        response = client.post("/applications/", json=payload)
        assert response.status_code == 400
        assert response.status_code != 500


class TestUpdateApplication:
    def test_update_existing_application_returns_200(
        self, client, supabase, applications_table, existing_applicant
    ):
        insert_response = (
            supabase.table(applications_table)
            .insert(
                {
                    "applicant_id": existing_applicant,
                    "programme": "B.Tech",
                    "department": "Pytest Update Dept",
                }
            )
            .execute()
        )
        application_id = insert_response.data[0]["id"]
        try:
            response = client.patch(
                f"/applications/{application_id}", json={"remarks": "Pytest updated remark"}
            )
            assert response.status_code == 200
            assert response.json()["remarks"] == "Pytest updated remark"
            assert response.json()["id"] == application_id
        finally:
            supabase.table(applications_table).delete().eq("id", application_id).execute()

    def test_update_nonexistent_application_returns_404(self, client):
        response = client.patch(
            "/applications/00000000-0000-0000-0000-000000000000",
            json={"remarks": "does not matter"},
        )
        assert response.status_code == 404

    def test_update_with_invalid_programme_returns_400(
        self, client, supabase, applications_table, existing_applicant
    ):
        # applications_programme_check restricts programme to a fixed set —
        # violating it via PATCH must be a handled 400, not a raw 500.
        insert_response = (
            supabase.table(applications_table)
            .insert(
                {
                    "applicant_id": existing_applicant,
                    "programme": "B.Tech",
                    "department": "Pytest Bad Patch Dept",
                }
            )
            .execute()
        )
        application_id = insert_response.data[0]["id"]
        try:
            response = client.patch(
                f"/applications/{application_id}",
                json={"programme": "Not-A-Real-Programme"},
            )
            assert response.status_code == 400
            assert response.status_code != 500
        finally:
            supabase.table(applications_table).delete().eq("id", application_id).execute()


class TestDeleteApplication:
    def test_delete_existing_application_returns_204(
        self, client, supabase, applications_table, existing_applicant
    ):
        insert_response = (
            supabase.table(applications_table)
            .insert(
                {
                    "applicant_id": existing_applicant,
                    "programme": "B.Tech",
                    "department": "Pytest Delete Dept",
                }
            )
            .execute()
        )
        application_id = insert_response.data[0]["id"]
        try:
            response = client.delete(f"/applications/{application_id}")
            assert response.status_code == 204
            follow_up = client.get(f"/applications/{application_id}")
            assert follow_up.status_code == 404
        finally:
            supabase.table(applications_table).delete().eq("id", application_id).execute()

    def test_delete_nonexistent_application_returns_404(self, client):
        response = client.delete("/applications/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404
