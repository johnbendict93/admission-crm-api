"""Tests for the /followups module (GET list, GET /{id}, POST, PATCH,
DELETE, soft-delete verification). Field names come directly from
app/models/followups.py (FollowupBase) and app/routers/followups.py.

Like call_schedules/campus_visits, followups has zero pre-existing seed
rows on dev (confirmed live, Sept 2026, before writing this module) - so
there's no "existing_followup" fixture pulling a row that's always
there. Every test that needs one creates and cleans up its own instead,
same pattern as tests/test_call_schedules.py. This table is FK'd to
leads, so fixtures here use the existing_lead fixture from conftest.py
as the FK target.

Note: this table is also read/written by the separate dce_crm Streamlit
app in production, but that app talks to prod, never dev - this suite
only ever touches DEV_DATABASE_URL/dev SUPABASE_URL (enforced by
conftest.py's pytest_configure safety gate), so it cannot interact with
that app's live data.
"""
import pytest


@pytest.fixture
def new_followup(supabase, followups_table, existing_lead):
    """Creates one followup row directly (bypassing the API, same as
    existing_lead/applicant/application do for setup), yields its id,
    and hard-deletes it afterward. Exists because this table has no
    pre-existing seed data to borrow."""
    insert_response = (
        supabase.table(followups_table)
        .insert({"lead_id": existing_lead, "called_by": "Priya Test Telecaller"})
        .execute()
    )
    followup_id = insert_response.data[0]["id"]
    yield followup_id
    supabase.table(followups_table).delete().eq("id", followup_id).execute()


class TestListFollowups:
    def test_list_returns_200(self, client, new_followup):
        response = client.get("/followups/")
        assert response.status_code == 200
        body = response.json()
        assert isinstance(body["items"], list)
        assert isinstance(body["total"], int)
        assert body["limit"] == 50
        assert body["offset"] == 0
        assert isinstance(body["has_more"], bool)

    def test_pagination_limit_is_respected(self, client, new_followup):
        response = client.get("/followups/?limit=1&offset=0")
        assert response.status_code == 200
        body = response.json()
        assert len(body["items"]) <= 1
        assert body["limit"] == 1
        assert body["offset"] == 0

    def test_pagination_total_and_has_more_are_accurate(
        self, client, supabase, followups_table, existing_lead
    ):
        # Deterministic regardless of whatever else is on dev: create two
        # known rows, then confirm `total` counts every matching row (not
        # just the page) and `has_more` reflects whether more rows exist
        # beyond the current page - not just that the array got sliced.
        id_a = (
            supabase.table(followups_table)
            .insert({"lead_id": existing_lead, "called_by": "Pytest Pagination A"})
            .execute()
        ).data[0]["id"]
        id_b = (
            supabase.table(followups_table)
            .insert({"lead_id": existing_lead, "called_by": "Pytest Pagination B"})
            .execute()
        ).data[0]["id"]
        try:
            page = client.get("/followups/?limit=1&offset=0")
            assert page.status_code == 200
            body = page.json()
            assert body["total"] >= 2
            assert body["has_more"] is True

            full_limit = min(body["total"], 200)
            full_page = client.get(f"/followups/?limit={full_limit}&offset=0")
            assert full_page.status_code == 200
            full_body = full_page.json()
            # The API caps limit at 200 (Query(..., le=200)), so once dev
            # has more than 200 rows in this table a single page can never
            # return every row. len(items) tracks full_limit (== min(total,
            # 200)), not total itself, and has_more is only False once
            # total actually fits within one page.
            assert len(full_body["items"]) == full_limit
            assert full_body["has_more"] is (full_body["total"] > full_limit)
        finally:
            supabase.table(followups_table).delete().eq("id", id_a).execute()
            supabase.table(followups_table).delete().eq("id", id_b).execute()


class TestGetFollowup:
    def test_get_existing_followup_returns_200(self, client, new_followup):
        response = client.get(f"/followups/{new_followup}")
        assert response.status_code == 200
        assert response.json()["id"] == new_followup

    def test_get_nonexistent_followup_returns_404(self, client):
        response = client.get("/followups/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404


class TestCreateFollowup:
    def test_create_followup_then_delete(
        self, client, supabase, followups_table, existing_lead
    ):
        payload = {
            "lead_id": existing_lead,
            "called_by": "Kavya New Telecaller",
            "call_date": "2026-10-01",
            "call_time": "10:30",
            "response": "Interested",
            "notes": "Will call back after discussing with parents.",
            "next_followup_date": "2026-10-08",
        }
        created_id = None
        try:
            response = client.post("/followups/", json=payload)
            assert response.status_code == 201
            body = response.json()
            created_id = body["id"]
            assert body["lead_id"] == payload["lead_id"]
            assert body["called_by"] == payload["called_by"]
            assert body["call_date"] == payload["call_date"]
            assert body["call_time"] == payload["call_time"]
            assert body["response"] == payload["response"]
            assert body["notes"] == payload["notes"]
            assert body["next_followup_date"] == payload["next_followup_date"]
        finally:
            if created_id:
                supabase.table(followups_table).delete().eq("id", created_id).execute()


class TestUpdateFollowup:
    def test_update_existing_followup_returns_200(self, client, new_followup):
        response = client.patch(
            f"/followups/{new_followup}", json={"response": "Not Interested"}
        )
        assert response.status_code == 200
        assert response.json()["response"] == "Not Interested"
        assert response.json()["id"] == new_followup

    def test_update_nonexistent_followup_returns_404(self, client):
        response = client.patch(
            "/followups/00000000-0000-0000-0000-000000000000",
            json={"response": "Not Interested"},
        )
        assert response.status_code == 404


class TestDeleteFollowup:
    def test_delete_existing_followup_returns_204(
        self, client, supabase, followups_table, existing_lead, admin_user_id
    ):
        insert_response = (
            supabase.table(followups_table)
            .insert({"lead_id": existing_lead, "called_by": "Delete-Test Telecaller"})
            .execute()
        )
        followup_id = insert_response.data[0]["id"]
        try:
            response = client.delete(f"/followups/{followup_id}")
            assert response.status_code == 204
            follow_up = client.get(f"/followups/{followup_id}")
            assert follow_up.status_code == 404

            # Soft delete, not hard delete — same check as every other module.
            row = (
                supabase.table(followups_table)
                .select("id,deleted_at,deleted_by")
                .eq("id", followup_id)
                .single()
                .execute()
            ).data
            assert row is not None, "row was hard-deleted, not soft-deleted"
            assert row["deleted_at"] is not None
            assert row["deleted_by"] == admin_user_id
        finally:
            supabase.table(followups_table).delete().eq("id", followup_id).execute()

    def test_delete_nonexistent_followup_returns_404(self, client):
        response = client.delete("/followups/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404

    def test_delete_already_deleted_followup_returns_404(
        self, client, supabase, followups_table, existing_lead
    ):
        insert_response = (
            supabase.table(followups_table)
            .insert({"lead_id": existing_lead, "called_by": "Double-Delete Telecaller"})
            .execute()
        )
        followup_id = insert_response.data[0]["id"]
        try:
            first = client.delete(f"/followups/{followup_id}")
            assert first.status_code == 204
            second = client.delete(f"/followups/{followup_id}")
            assert second.status_code == 404
        finally:
            supabase.table(followups_table).delete().eq("id", followup_id).execute()
