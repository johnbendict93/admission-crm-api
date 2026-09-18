"""Tests for the /hostel-allotments module (GET list, GET /{id}, POST,
PATCH, DELETE, soft-delete verification). Field names come directly from
app/models/hostel_allotments.py (HostelAllotmentBase) and
app/routers/hostel_allotments.py.

Like fee_payments/scholarships, hostel_allotments has zero pre-existing
seed rows on dev (confirmed live, Sept 2026, before writing this module)
- so there's no "existing_hostel_allotment" fixture pulling a row that's
always there. Every test that needs one creates and cleans up its own
instead, same pattern as tests/test_fee_payments.py and
tests/test_scholarships.py.
"""
import pytest


@pytest.fixture
def new_hostel_allotment(supabase, hostel_allotments_table, existing_applicant):
    """Creates one hostel_allotment row directly (bypassing the API, same
    as existing_lead/applicant/application do for setup), yields its id,
    and hard-deletes it afterward. Exists because this table has no
    pre-existing seed data to borrow."""
    insert_response = (
        supabase.table(hostel_allotments_table)
        .insert(
            {
                "applicant_id": existing_applicant,
                "block_name": "A Block",
                "room_number": "101",
            }
        )
        .execute()
    )
    hostel_allotment_id = insert_response.data[0]["id"]
    yield hostel_allotment_id
    supabase.table(hostel_allotments_table).delete().eq("id", hostel_allotment_id).execute()


class TestListHostelAllotments:
    def test_list_returns_200(self, client, new_hostel_allotment):
        response = client.get("/hostel-allotments/")
        assert response.status_code == 200
        body = response.json()
        assert isinstance(body["items"], list)
        assert isinstance(body["total"], int)
        assert body["limit"] == 50
        assert body["offset"] == 0
        assert isinstance(body["has_more"], bool)

    def test_pagination_limit_is_respected(self, client, new_hostel_allotment):
        response = client.get("/hostel-allotments/?limit=1&offset=0")
        assert response.status_code == 200
        body = response.json()
        assert len(body["items"]) <= 1
        assert body["limit"] == 1
        assert body["offset"] == 0

    def test_pagination_total_and_has_more_are_accurate(
        self, client, supabase, hostel_allotments_table, existing_applicant
    ):
        # Deterministic regardless of whatever else is on dev: create two
        # known rows, then confirm `total` counts every matching row (not
        # just the page) and `has_more` reflects whether more rows exist
        # beyond the current page - not just that the array got sliced.
        id_a = (
            supabase.table(hostel_allotments_table)
            .insert({"applicant_id": existing_applicant, "block_name": "Pagination Block", "room_number": "PA1"})
            .execute()
        ).data[0]["id"]
        id_b = (
            supabase.table(hostel_allotments_table)
            .insert({"applicant_id": existing_applicant, "block_name": "Pagination Block", "room_number": "PA2"})
            .execute()
        ).data[0]["id"]
        try:
            page = client.get("/hostel-allotments/?limit=1&offset=0")
            assert page.status_code == 200
            body = page.json()
            assert body["total"] >= 2
            assert body["has_more"] is True

            full_limit = min(body["total"], 200)
            full_page = client.get(f"/hostel-allotments/?limit={full_limit}&offset=0")
            assert full_page.status_code == 200
            full_body = full_page.json()
            assert len(full_body["items"]) == full_body["total"]
            assert full_body["has_more"] is False
        finally:
            supabase.table(hostel_allotments_table).delete().eq("id", id_a).execute()
            supabase.table(hostel_allotments_table).delete().eq("id", id_b).execute()


class TestGetHostelAllotment:
    def test_get_existing_hostel_allotment_returns_200(self, client, new_hostel_allotment):
        response = client.get(f"/hostel-allotments/{new_hostel_allotment}")
        assert response.status_code == 200
        assert response.json()["id"] == new_hostel_allotment

    def test_get_nonexistent_hostel_allotment_returns_404(self, client):
        response = client.get("/hostel-allotments/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404


class TestCreateHostelAllotment:
    def test_create_hostel_allotment_then_delete(
        self, client, supabase, hostel_allotments_table, existing_applicant
    ):
        payload = {
            "applicant_id": existing_applicant,
            "block_name": "B Block",
            "room_number": "202",
            "room_type": "Single",
        }
        created_id = None
        try:
            response = client.post("/hostel-allotments/", json=payload)
            assert response.status_code == 201
            body = response.json()
            created_id = body["id"]
            assert body["applicant_id"] == payload["applicant_id"]
            assert body["block_name"] == payload["block_name"]
            assert body["room_number"] == payload["room_number"]
            assert body["room_type"] == payload["room_type"]
            # DB defaults apply when the request omits these.
            assert body["allotment_date"] is not None
            assert body["academic_year"] == "2026-27"
            assert body["status"] == "Active"
        finally:
            if created_id:
                supabase.table(hostel_allotments_table).delete().eq("id", created_id).execute()


class TestUpdateHostelAllotment:
    def test_update_existing_hostel_allotment_returns_200(self, client, new_hostel_allotment):
        response = client.patch(
            f"/hostel-allotments/{new_hostel_allotment}", json={"status": "Vacated"}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "Vacated"
        assert response.json()["id"] == new_hostel_allotment

    def test_update_nonexistent_hostel_allotment_returns_404(self, client):
        response = client.patch(
            "/hostel-allotments/00000000-0000-0000-0000-000000000000",
            json={"status": "Vacated"},
        )
        assert response.status_code == 404


class TestDeleteHostelAllotment:
    def test_delete_existing_hostel_allotment_returns_204(
        self, client, supabase, hostel_allotments_table, existing_applicant, admin_user_id
    ):
        insert_response = (
            supabase.table(hostel_allotments_table)
            .insert(
                {
                    "applicant_id": existing_applicant,
                    "block_name": "C Block",
                    "room_number": "303",
                }
            )
            .execute()
        )
        hostel_allotment_id = insert_response.data[0]["id"]
        try:
            response = client.delete(f"/hostel-allotments/{hostel_allotment_id}")
            assert response.status_code == 204
            follow_up = client.get(f"/hostel-allotments/{hostel_allotment_id}")
            assert follow_up.status_code == 404

            # Soft delete, not hard delete — same check as every other module.
            row = (
                supabase.table(hostel_allotments_table)
                .select("id,deleted_at,deleted_by")
                .eq("id", hostel_allotment_id)
                .single()
                .execute()
            ).data
            assert row is not None, "row was hard-deleted, not soft-deleted"
            assert row["deleted_at"] is not None
            assert row["deleted_by"] == admin_user_id
        finally:
            supabase.table(hostel_allotments_table).delete().eq("id", hostel_allotment_id).execute()

    def test_delete_nonexistent_hostel_allotment_returns_404(self, client):
        response = client.delete("/hostel-allotments/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404

    def test_delete_already_deleted_hostel_allotment_returns_404(
        self, client, supabase, hostel_allotments_table, existing_applicant
    ):
        insert_response = (
            supabase.table(hostel_allotments_table)
            .insert(
                {
                    "applicant_id": existing_applicant,
                    "block_name": "D Block",
                    "room_number": "404",
                }
            )
            .execute()
        )
        hostel_allotment_id = insert_response.data[0]["id"]
        try:
            first = client.delete(f"/hostel-allotments/{hostel_allotment_id}")
            assert first.status_code == 204
            second = client.delete(f"/hostel-allotments/{hostel_allotment_id}")
            assert second.status_code == 404
        finally:
            supabase.table(hostel_allotments_table).delete().eq("id", hostel_allotment_id).execute()
