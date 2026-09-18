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
        body = response.json()
        assert isinstance(body["items"], list)
        assert isinstance(body["total"], int)
        assert body["limit"] == 50
        assert body["offset"] == 0
        assert isinstance(body["has_more"], bool)

    def test_pagination_limit_is_respected(self, client, new_call_schedule):
        response = client.get("/call-schedules/?limit=1&offset=0")
        assert response.status_code == 200
        body = response.json()
        assert len(body["items"]) <= 1
        assert body["limit"] == 1
        assert body["offset"] == 0

    def test_pagination_total_and_has_more_are_accurate(
        self, client, supabase, call_schedules_table, existing_lead
    ):
        # Deterministic regardless of whatever else is on dev: create two
        # known rows, then confirm `total` counts every matching row (not
        # just the page) and `has_more` reflects whether more rows exist
        # beyond the current page - not just that the array got sliced.
        id_a = (
            supabase.table(call_schedules_table)
            .insert({"lead_id": existing_lead, "scheduled_by": "Pytest Pagination A"})
            .execute()
        ).data[0]["id"]
        id_b = (
            supabase.table(call_schedules_table)
            .insert({"lead_id": existing_lead, "scheduled_by": "Pytest Pagination B"})
            .execute()
        ).data[0]["id"]
        try:
            page = client.get("/call-schedules/?limit=1&offset=0")
            assert page.status_code == 200
            body = page.json()
            assert body["total"] >= 2
            assert body["has_more"] is True

            full_limit = min(body["total"], 200)
            full_page = client.get(f"/call-schedules/?limit={full_limit}&offset=0")
            assert full_page.status_code == 200
            full_body = full_page.json()
            assert len(full_body["items"]) == full_body["total"]
            assert full_body["has_more"] is False
        finally:
            supabase.table(call_schedules_table).delete().eq("id", id_a).execute()
            supabase.table(call_schedules_table).delete().eq("id", id_b).execute()


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
            "scheduled_time": "2026-10-01T10:30:00+05:30",
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


class TestCallScheduleErrorHandling:
    """scheduled_time must carry an explicit UTC offset - see
    app/models/call_schedules.py's _require_tz_aware_scheduled_time.
    A naive value is rejected at request-parsing time (Pydantic), which
    FastAPI surfaces as 422, not the 400 used elsewhere in this project
    for DB-level (CHECK constraint) validation errors - a deliberate,
    documented distinction: this is a malformed-request problem, not a
    business-rule violation the database enforces."""

    def test_naive_scheduled_time_rejected_on_create(self, client, existing_lead):
        response = client.post(
            "/call-schedules/",
            json={
                "lead_id": existing_lead,
                "scheduled_by": "Naive Time Telecaller",
                "scheduled_time": "2026-10-01T10:30:00",
            },
        )
        assert response.status_code == 422

    def test_offset_aware_scheduled_time_accepted_on_create(
        self, client, supabase, call_schedules_table, existing_lead
    ):
        payload = {
            "lead_id": existing_lead,
            "scheduled_by": "Offset Aware Telecaller",
            "scheduled_time": "2026-10-01T10:30:00+05:30",
        }
        created_id = None
        try:
            response = client.post("/call-schedules/", json=payload)
            assert response.status_code == 201
            created_id = response.json()["id"]
        finally:
            if created_id:
                supabase.table(call_schedules_table).delete().eq("id", created_id).execute()

    def test_naive_scheduled_time_rejected_on_update(self, client, new_call_schedule):
        response = client.patch(
            f"/call-schedules/{new_call_schedule}",
            json={"scheduled_time": "2026-10-02T11:00:00"},
        )
        assert response.status_code == 422

    def test_offset_aware_scheduled_time_accepted_on_update(self, client, new_call_schedule):
        response = client.patch(
            f"/call-schedules/{new_call_schedule}",
            json={"scheduled_time": "2026-10-02T11:00:00+05:30"},
        )
        assert response.status_code == 200


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
