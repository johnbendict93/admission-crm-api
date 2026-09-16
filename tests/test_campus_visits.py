"""Tests for the /campus-visits module (GET list, GET /{id}, POST, PATCH,
DELETE, soft-delete verification). Field names come directly from
app/models/campus_visits.py (CampusVisitBase) and
app/routers/campus_visits.py.

Like call_schedules, campus_visits has zero pre-existing seed rows on
dev (confirmed live, Sept 2026, before writing this module) - so there's
no "existing_campus_visit" fixture pulling a row that's always there.
Every test that needs one creates and cleans up its own instead, same
pattern as tests/test_call_schedules.py. This table is FK'd to leads, so
fixtures here use the existing_lead fixture from conftest.py as the FK
target.
"""
import pytest


@pytest.fixture
def new_campus_visit(supabase, campus_visits_table, existing_lead):
    """Creates one campus_visit row directly (bypassing the API, same as
    existing_lead/applicant/application do for setup), yields its id, and
    hard-deletes it afterward. Exists because this table has no
    pre-existing seed data to borrow."""
    insert_response = (
        supabase.table(campus_visits_table)
        .insert({"lead_id": existing_lead, "visited_by": "Priya Test Telecaller"})
        .execute()
    )
    campus_visit_id = insert_response.data[0]["id"]
    yield campus_visit_id
    supabase.table(campus_visits_table).delete().eq("id", campus_visit_id).execute()


class TestListCampusVisits:
    def test_list_returns_200(self, client, new_campus_visit):
        response = client.get("/campus-visits/")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_pagination_limit_is_respected(self, client, new_campus_visit):
        response = client.get("/campus-visits/?limit=1&offset=0")
        assert response.status_code == 200
        assert len(response.json()) <= 1


class TestGetCampusVisit:
    def test_get_existing_campus_visit_returns_200(self, client, new_campus_visit):
        response = client.get(f"/campus-visits/{new_campus_visit}")
        assert response.status_code == 200
        assert response.json()["id"] == new_campus_visit

    def test_get_nonexistent_campus_visit_returns_404(self, client):
        response = client.get("/campus-visits/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404


class TestCreateCampusVisit:
    def test_create_campus_visit_then_delete(
        self, client, supabase, campus_visits_table, existing_lead
    ):
        payload = {
            "lead_id": existing_lead,
            "visit_date": "2026-10-05",
            "visited_by": "Kavya New Telecaller",
            "departments_seen": "AI & Data Science, CSE",
            "outcome": "Interested",
            "notes": "Parent accompanied; requested fee structure.",
        }
        created_id = None
        try:
            response = client.post("/campus-visits/", json=payload)
            assert response.status_code == 201
            body = response.json()
            created_id = body["id"]
            assert body["lead_id"] == payload["lead_id"]
            assert body["visit_date"] == payload["visit_date"]
            assert body["visited_by"] == payload["visited_by"]
            assert body["departments_seen"] == payload["departments_seen"]
            assert body["outcome"] == payload["outcome"]
            assert body["notes"] == payload["notes"]
        finally:
            if created_id:
                supabase.table(campus_visits_table).delete().eq("id", created_id).execute()


class TestUpdateCampusVisit:
    def test_update_existing_campus_visit_returns_200(self, client, new_campus_visit):
        response = client.patch(
            f"/campus-visits/{new_campus_visit}", json={"outcome": "Admitted"}
        )
        assert response.status_code == 200
        assert response.json()["outcome"] == "Admitted"
        assert response.json()["id"] == new_campus_visit

    def test_update_nonexistent_campus_visit_returns_404(self, client):
        response = client.patch(
            "/campus-visits/00000000-0000-0000-0000-000000000000",
            json={"outcome": "Admitted"},
        )
        assert response.status_code == 404


class TestDeleteCampusVisit:
    def test_delete_existing_campus_visit_returns_204(
        self, client, supabase, campus_visits_table, existing_lead, admin_user_id
    ):
        insert_response = (
            supabase.table(campus_visits_table)
            .insert({"lead_id": existing_lead, "visited_by": "Delete-Test Telecaller"})
            .execute()
        )
        campus_visit_id = insert_response.data[0]["id"]
        try:
            response = client.delete(f"/campus-visits/{campus_visit_id}")
            assert response.status_code == 204
            follow_up = client.get(f"/campus-visits/{campus_visit_id}")
            assert follow_up.status_code == 404

            # Soft delete, not hard delete — same check as every other module.
            row = (
                supabase.table(campus_visits_table)
                .select("id,deleted_at,deleted_by")
                .eq("id", campus_visit_id)
                .single()
                .execute()
            ).data
            assert row is not None, "row was hard-deleted, not soft-deleted"
            assert row["deleted_at"] is not None
            assert row["deleted_by"] == admin_user_id
        finally:
            supabase.table(campus_visits_table).delete().eq("id", campus_visit_id).execute()

    def test_delete_nonexistent_campus_visit_returns_404(self, client):
        response = client.delete("/campus-visits/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404

    def test_delete_already_deleted_campus_visit_returns_404(
        self, client, supabase, campus_visits_table, existing_lead
    ):
        insert_response = (
            supabase.table(campus_visits_table)
            .insert({"lead_id": existing_lead, "visited_by": "Double-Delete Telecaller"})
            .execute()
        )
        campus_visit_id = insert_response.data[0]["id"]
        try:
            first = client.delete(f"/campus-visits/{campus_visit_id}")
            assert first.status_code == 204
            second = client.delete(f"/campus-visits/{campus_visit_id}")
            assert second.status_code == 404
        finally:
            supabase.table(campus_visits_table).delete().eq("id", campus_visit_id).execute()
