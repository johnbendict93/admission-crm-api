"""Tests for the /call-schedules module (GET list, GET /{id}, POST, PATCH,
DELETE, soft-delete verification). Field names come directly from
app/models/call_schedules.py (CallScheduleBase) and
app/routers/call_schedules.py.

Like telecallers/document_types/lookup_values, call_schedules has zero
pre-existing seed rows on dev (confirmed live, Sept 2026, before writing
this module) - so there's no "existing_call_schedule" fixture pulling a
row that's always there. Every test that needs one creates and cleans up
its own instead, same pattern as tests/test_telecallers.py. Unlike
telecallers, this table IS FK'd to leads, so fixtures here need the
existing_lead fixture from conftest.py as the FK target.
"""
import pytest


@pytest.fixture
def new_call_schedule(supabase, call_schedules_table, existing_lead):
    """Creates one call_schedule row directly (bypassing the API, same as
    existing_lead/applicant/application do for setup), yields its id, and
    hard-deletes it afterward. Exists because this table has no
    pre-existing seed data to borrow."""
    insert_response = (
        supabase.table(call_schedules_table)
        .insert({"lead_id": existing_lead, "scheduled_by": "Priya Test Telecaller"})
        .execute()
    )
    call_schedule_id = insert_response.data[0]["id"]
    yield call_schedule_id
    supabase.table(call_schedules_table).delete().eq("id", call_schedule_id).execute()


class TestListCallSchedules:
    def test_list_returns_200(self, client, new_call_schedule):
        response = client.get("/call-schedules/")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_pagination_limit_is_respected(self, client, new_call_schedule):
        response = client.get("/call-schedules/?limit=1&offset=0")
        assert response.status_code == 200
        assert len(response.json()) <= 1


class TestGetCallSchedule:
    def test_get_existing_call_schedule_returns_200(self, client, new_call_schedule):
        response = client.get(f"/call-schedules/{new_call_schedule}")
        assert response.status_code == 200
        assert response.json()["id"] == new_call_schedule

    def test_get_nonexistent_call_schedule_returns_404(self, client):
        response = client.get("/call-schedules/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404


class TestCreateCallSchedule:
    def test_create_call_schedule_then_delete(
        self, client, supabase, call_schedules_table, existing_lead
    ):
        payload = {
            "lead_id": existing_lead,
            "scheduled_by": "Kavya New Telecaller",
            "scheduled_time": "2026-10-01T10:30:00",
        }
        created_id = None
        try:
            response = client.post("/call-schedules/", json=payload)
            assert response.status_code == 201
            body = response.json()
            created_id = body["id"]
            assert body["lead_id"] == payload["lead_id"]
            assert body["scheduled_by"] == payload["scheduled_by"]
            # DB defaults apply when the request omits these.
            assert body["reminder_sent"] is False
            assert body["status"] == "Pending"
        finally:
            if created_id:
                supabase.table(call_schedules_table).delete().eq("id", created_id).execute()


class TestUpdateCallSchedule:
    def test_update_existing_call_schedule_returns_200(self, client, new_call_schedule):
        response = client.patch(
            f"/call-schedules/{new_call_schedule}", json={"status": "Completed"}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "Completed"
        assert response.json()["id"] == new_call_schedule

    def test_update_nonexistent_call_schedule_returns_404(self, client):
        response = client.patch(
            "/call-schedules/00000000-0000-0000-0000-000000000000",
            json={"status": "Completed"},
        )
        assert response.status_code == 404


class TestDeleteCallSchedule:
    def test_delete_existing_call_schedule_returns_204(
        self, client, supabase, call_schedules_table, existing_lead, admin_user_id
    ):
        insert_response = (
            supabase.table(call_schedules_table)
            .insert({"lead_id": existing_lead, "scheduled_by": "Delete-Test Telecaller"})
            .execute()
        )
        call_schedule_id = insert_response.data[0]["id"]
        try:
            response = client.delete(f"/call-schedules/{call_schedule_id}")
            assert response.status_code == 204
            follow_up = client.get(f"/call-schedules/{call_schedule_id}")
            assert follow_up.status_code == 404

            # Soft delete, not hard delete — same check as every other module.
            row = (
                supabase.table(call_schedules_table)
                .select("id,deleted_at,deleted_by")
                .eq("id", call_schedule_id)
                .single()
                .execute()
            ).data
            assert row is not None, "row was hard-deleted, not soft-deleted"
            assert row["deleted_at"] is not None
            assert row["deleted_by"] == admin_user_id
        finally:
            supabase.table(call_schedules_table).delete().eq("id", call_schedule_id).execute()

    def test_delete_nonexistent_call_schedule_returns_404(self, client):
        response = client.delete("/call-schedules/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404

    def test_delete_already_deleted_call_schedule_returns_404(
        self, client, supabase, call_schedules_table, existing_lead
    ):
        insert_response = (
            supabase.table(call_schedules_table)
            .insert({"lead_id": existing_lead, "scheduled_by": "Double-Delete Telecaller"})
            .execute()
        )
        call_schedule_id = insert_response.data[0]["id"]
        try:
            first = client.delete(f"/call-schedules/{call_schedule_id}")
            assert first.status_code == 204
            second = client.delete(f"/call-schedules/{call_schedule_id}")
            assert second.status_code == 404
        finally:
            supabase.table(call_schedules_table).delete().eq("id", call_schedule_id).execute()
