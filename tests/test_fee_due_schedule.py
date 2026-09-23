"""Tests for the /fee-due-schedule module (GET list, GET /{id}, POST,
PATCH, DELETE, soft-delete verification). Field names come directly from
app/models/fee_due_schedule.py (FeeDueScheduleBase) and
app/routers/fee_due_schedule.py.

Same pattern as tests/test_fee_payments.py: every test that needs a row
creates and cleans up its own (via supabase directly, bypassing the API,
same as existing_lead/applicant/application do for setup) rather than
relying on scripts/seed_dev_fee_due_schedule.py's data always being
present in a particular shape.
"""
import pytest


@pytest.fixture
def new_fee_due_schedule(supabase, fee_due_schedule_table, existing_applicant):
    """Creates one fee_due_schedule row directly, yields its id, and
    hard-deletes it afterward."""
    insert_response = (
        supabase.table(fee_due_schedule_table)
        .insert(
            {
                "applicant_id": existing_applicant,
                "fee_component": "Tuition Fee",
                "amount_due": 50000,
                "due_date": "2027-01-15",
            }
        )
        .execute()
    )
    fee_due_schedule_id = insert_response.data[0]["id"]
    yield fee_due_schedule_id
    supabase.table(fee_due_schedule_table).delete().eq("id", fee_due_schedule_id).execute()


class TestListFeeDueSchedules:
    def test_list_returns_200(self, client, new_fee_due_schedule):
        response = client.get("/fee-due-schedule/")
        assert response.status_code == 200
        body = response.json()
        assert isinstance(body["items"], list)
        assert isinstance(body["total"], int)
        assert body["limit"] == 50
        assert body["offset"] == 0
        assert isinstance(body["has_more"], bool)

    def test_pagination_limit_is_respected(self, client, new_fee_due_schedule):
        response = client.get("/fee-due-schedule/?limit=1&offset=0")
        assert response.status_code == 200
        body = response.json()
        assert len(body["items"]) <= 1
        assert body["limit"] == 1
        assert body["offset"] == 0

    def test_pagination_total_and_has_more_are_accurate(
        self, client, supabase, fee_due_schedule_table, existing_applicant
    ):
        # Deterministic regardless of whatever else is on dev (95 seeded
        # rows from module 18 or otherwise): create two known rows, then
        # confirm `total` counts every matching row (not just the page)
        # and `has_more` reflects the page cap, not just whether the array
        # got sliced - same fix applied to test_leads.py/test_followups.py
        # this session once those tables grew past the 200-row page cap.
        id_a = (
            supabase.table(fee_due_schedule_table)
            .insert({"applicant_id": existing_applicant, "fee_component": "Tuition Fee", "amount_due": 100, "due_date": "2027-01-01"})
            .execute()
        ).data[0]["id"]
        id_b = (
            supabase.table(fee_due_schedule_table)
            .insert({"applicant_id": existing_applicant, "fee_component": "Tuition Fee", "amount_due": 200, "due_date": "2027-01-02"})
            .execute()
        ).data[0]["id"]
        try:
            page = client.get("/fee-due-schedule/?limit=1&offset=0")
            assert page.status_code == 200
            body = page.json()
            assert body["total"] >= 2
            assert body["has_more"] is True

            full_limit = min(body["total"], 200)
            full_page = client.get(f"/fee-due-schedule/?limit={full_limit}&offset=0")
            assert full_page.status_code == 200
            full_body = full_page.json()
            assert len(full_body["items"]) == full_limit
            assert full_body["has_more"] is (full_body["total"] > full_limit)
        finally:
            supabase.table(fee_due_schedule_table).delete().eq("id", id_a).execute()
            supabase.table(fee_due_schedule_table).delete().eq("id", id_b).execute()


class TestGetFeeDueSchedule:
    def test_get_existing_fee_due_schedule_returns_200(self, client, new_fee_due_schedule):
        response = client.get(f"/fee-due-schedule/{new_fee_due_schedule}")
        assert response.status_code == 200
        assert response.json()["id"] == new_fee_due_schedule

    def test_get_nonexistent_fee_due_schedule_returns_404(self, client):
        response = client.get("/fee-due-schedule/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404


class TestCreateFeeDueSchedule:
    def test_create_fee_due_schedule_then_delete(
        self, client, supabase, fee_due_schedule_table, existing_applicant
    ):
        payload = {
            "applicant_id": existing_applicant,
            "fee_component": "Hostel Fee",
            "amount_due": 15000.50,
            "due_date": "2027-02-01",
        }
        created_id = None
        try:
            response = client.post("/fee-due-schedule/", json=payload)
            assert response.status_code == 201
            body = response.json()
            created_id = body["id"]
            assert body["applicant_id"] == payload["applicant_id"]
            assert body["fee_component"] == payload["fee_component"]
            assert body["amount_due"] == payload["amount_due"]
            assert body["due_date"] == payload["due_date"]
            # DB default applies when the request omits this.
            assert body["academic_year"] == "2026-27"
        finally:
            if created_id:
                supabase.table(fee_due_schedule_table).delete().eq("id", created_id).execute()


class TestUpdateFeeDueSchedule:
    def test_update_existing_fee_due_schedule_returns_200(self, client, new_fee_due_schedule):
        response = client.patch(
            f"/fee-due-schedule/{new_fee_due_schedule}", json={"amount_due": 60000}
        )
        assert response.status_code == 200
        assert response.json()["amount_due"] == 60000
        assert response.json()["id"] == new_fee_due_schedule

    def test_update_nonexistent_fee_due_schedule_returns_404(self, client):
        response = client.patch(
            "/fee-due-schedule/00000000-0000-0000-0000-000000000000",
            json={"amount_due": 1000},
        )
        assert response.status_code == 404


class TestDeleteFeeDueSchedule:
    def test_delete_existing_fee_due_schedule_returns_204(
        self, client, supabase, fee_due_schedule_table, existing_applicant, admin_user_id
    ):
        insert_response = (
            supabase.table(fee_due_schedule_table)
            .insert(
                {
                    "applicant_id": existing_applicant,
                    "fee_component": "Exam Fee",
                    "amount_due": 500,
                    "due_date": "2027-03-01",
                }
            )
            .execute()
        )
        fee_due_schedule_id = insert_response.data[0]["id"]
        try:
            response = client.delete(f"/fee-due-schedule/{fee_due_schedule_id}")
            assert response.status_code == 204
            follow_up = client.get(f"/fee-due-schedule/{fee_due_schedule_id}")
            assert follow_up.status_code == 404

            # Soft delete, not hard delete — same check as every other module.
            row = (
                supabase.table(fee_due_schedule_table)
                .select("id,deleted_at,deleted_by")
                .eq("id", fee_due_schedule_id)
                .single()
                .execute()
            ).data
            assert row is not None, "row was hard-deleted, not soft-deleted"
            assert row["deleted_at"] is not None
            assert row["deleted_by"] == admin_user_id
        finally:
            supabase.table(fee_due_schedule_table).delete().eq("id", fee_due_schedule_id).execute()

    def test_delete_nonexistent_fee_due_schedule_returns_404(self, client):
        response = client.delete("/fee-due-schedule/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404

    def test_delete_already_deleted_fee_due_schedule_returns_404(
        self, client, supabase, fee_due_schedule_table, existing_applicant
    ):
        insert_response = (
            supabase.table(fee_due_schedule_table)
            .insert(
                {
                    "applicant_id": existing_applicant,
                    "fee_component": "Lab Fee",
                    "amount_due": 1000,
                    "due_date": "2027-04-01",
                }
            )
            .execute()
        )
        fee_due_schedule_id = insert_response.data[0]["id"]
        try:
            first = client.delete(f"/fee-due-schedule/{fee_due_schedule_id}")
            assert first.status_code == 204
            second = client.delete(f"/fee-due-schedule/{fee_due_schedule_id}")
            assert second.status_code == 404
        finally:
            supabase.table(fee_due_schedule_table).delete().eq("id", fee_due_schedule_id).execute()
