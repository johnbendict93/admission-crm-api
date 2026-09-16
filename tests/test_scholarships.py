"""Tests for the /scholarships module (GET list, GET /{id}, POST, PATCH,
DELETE, soft-delete verification). Field names come directly from
app/models/scholarships.py (ScholarshipBase) and
app/routers/scholarships.py.

Like fee_payments, scholarships has zero pre-existing seed rows on dev
(confirmed live, Sept 2026, before writing this module) - so there's no
"existing_scholarship" fixture pulling a row that's always there. Every
test that needs one creates and cleans up its own instead, same pattern
as tests/test_fee_payments.py.
"""
import pytest


@pytest.fixture
def new_scholarship(supabase, scholarships_table, existing_applicant):
    """Creates one scholarship row directly (bypassing the API, same as
    existing_lead/applicant/application do for setup), yields its id, and
    hard-deletes it afterward. Exists because this table has no
    pre-existing seed data to borrow."""
    insert_response = (
        supabase.table(scholarships_table)
        .insert(
            {
                "applicant_id": existing_applicant,
                "scholarship_type": "Merit Scholarship",
            }
        )
        .execute()
    )
    scholarship_id = insert_response.data[0]["id"]
    yield scholarship_id
    supabase.table(scholarships_table).delete().eq("id", scholarship_id).execute()


class TestListScholarships:
    def test_list_returns_200(self, client, new_scholarship):
        response = client.get("/scholarships/")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_pagination_limit_is_respected(self, client, new_scholarship):
        response = client.get("/scholarships/?limit=1&offset=0")
        assert response.status_code == 200
        assert len(response.json()) <= 1


class TestGetScholarship:
    def test_get_existing_scholarship_returns_200(self, client, new_scholarship):
        response = client.get(f"/scholarships/{new_scholarship}")
        assert response.status_code == 200
        assert response.json()["id"] == new_scholarship

    def test_get_nonexistent_scholarship_returns_404(self, client):
        response = client.get("/scholarships/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404


class TestCreateScholarship:
    def test_create_scholarship_then_delete(
        self, client, supabase, scholarships_table, existing_applicant
    ):
        payload = {
            "applicant_id": existing_applicant,
            "scholarship_type": "Sports Scholarship",
            "amount": 10000,
            "reference_no": "PYTEST-SCH-0001",
        }
        created_id = None
        try:
            response = client.post("/scholarships/", json=payload)
            assert response.status_code == 201
            body = response.json()
            created_id = body["id"]
            assert body["applicant_id"] == payload["applicant_id"]
            assert body["scholarship_type"] == payload["scholarship_type"]
            assert body["amount"] == payload["amount"]
            assert body["reference_no"] == payload["reference_no"]
            # DB defaults apply when the request omits these.
            assert body["academic_year"] == "2026-27"
            assert body["status"] == "Applied"
        finally:
            if created_id:
                supabase.table(scholarships_table).delete().eq("id", created_id).execute()


class TestUpdateScholarship:
    def test_update_existing_scholarship_returns_200(self, client, new_scholarship):
        response = client.patch(
            f"/scholarships/{new_scholarship}", json={"status": "Approved"}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "Approved"
        assert response.json()["id"] == new_scholarship

    def test_update_nonexistent_scholarship_returns_404(self, client):
        response = client.patch(
            "/scholarships/00000000-0000-0000-0000-000000000000",
            json={"status": "Approved"},
        )
        assert response.status_code == 404


class TestDeleteScholarship:
    def test_delete_existing_scholarship_returns_204(
        self, client, supabase, scholarships_table, existing_applicant, admin_user_id
    ):
        insert_response = (
            supabase.table(scholarships_table)
            .insert(
                {
                    "applicant_id": existing_applicant,
                    "scholarship_type": "Need-Based Scholarship",
                }
            )
            .execute()
        )
        scholarship_id = insert_response.data[0]["id"]
        try:
            response = client.delete(f"/scholarships/{scholarship_id}")
            assert response.status_code == 204
            follow_up = client.get(f"/scholarships/{scholarship_id}")
            assert follow_up.status_code == 404

            # Soft delete, not hard delete — same check as every other module.
            row = (
                supabase.table(scholarships_table)
                .select("id,deleted_at,deleted_by")
                .eq("id", scholarship_id)
                .single()
                .execute()
            ).data
            assert row is not None, "row was hard-deleted, not soft-deleted"
            assert row["deleted_at"] is not None
            assert row["deleted_by"] == admin_user_id
        finally:
            supabase.table(scholarships_table).delete().eq("id", scholarship_id).execute()

    def test_delete_nonexistent_scholarship_returns_404(self, client):
        response = client.delete("/scholarships/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404

    def test_delete_already_deleted_scholarship_returns_404(
        self, client, supabase, scholarships_table, existing_applicant
    ):
        insert_response = (
            supabase.table(scholarships_table)
            .insert(
                {
                    "applicant_id": existing_applicant,
                    "scholarship_type": "Alumni Scholarship",
                }
            )
            .execute()
        )
        scholarship_id = insert_response.data[0]["id"]
        try:
            first = client.delete(f"/scholarships/{scholarship_id}")
            assert first.status_code == 204
            second = client.delete(f"/scholarships/{scholarship_id}")
            assert second.status_code == 404
        finally:
            supabase.table(scholarships_table).delete().eq("id", scholarship_id).execute()
