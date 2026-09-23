"""Tests for the /enquiry-monthly-history module (GET list, GET /{id},
POST, PATCH, DELETE, soft-delete verification). Field names come directly
from app/models/enquiry_monthly_history.py (EnquiryMonthlyHistoryBase) and
app/routers/enquiry_monthly_history.py.

No FK on this table (unlike fee_due_schedule) - it just needs a (year,
month) pair. UNIQUE(year, month) is a real DB constraint though, so every
test here uses year=1901 (a sentinel value no real or synthetic history
row would ever plausibly use - scripts/seed_dev_enquiry_monthly_history.py
only ever writes 2023 onward, and real leads-derived data is even more
recent), with a distinct month per test so nothing collides even if two
tests' rows briefly coexist.
"""
import pytest


@pytest.fixture
def new_enquiry_monthly_history(supabase, enquiry_monthly_history_table):
    """Creates one enquiry_monthly_history row directly, yields its id,
    and hard-deletes it afterward."""
    insert_response = (
        supabase.table(enquiry_monthly_history_table)
        .insert({"year": 1901, "month": 1, "enquiry_count": 42})
        .execute()
    )
    row_id = insert_response.data[0]["id"]
    yield row_id
    supabase.table(enquiry_monthly_history_table).delete().eq("id", row_id).execute()


class TestListEnquiryMonthlyHistory:
    def test_list_returns_200(self, client, new_enquiry_monthly_history):
        response = client.get("/enquiry-monthly-history/")
        assert response.status_code == 200
        body = response.json()
        assert isinstance(body["items"], list)
        assert isinstance(body["total"], int)
        assert body["limit"] == 50
        assert body["offset"] == 0
        assert isinstance(body["has_more"], bool)

    def test_pagination_limit_is_respected(self, client, new_enquiry_monthly_history):
        response = client.get("/enquiry-monthly-history/?limit=1&offset=0")
        assert response.status_code == 200
        body = response.json()
        assert len(body["items"]) <= 1
        assert body["limit"] == 1
        assert body["offset"] == 0

    def test_pagination_total_and_has_more_are_accurate(
        self, client, supabase, enquiry_monthly_history_table
    ):
        id_a = (
            supabase.table(enquiry_monthly_history_table)
            .insert({"year": 1901, "month": 2, "enquiry_count": 10})
            .execute()
        ).data[0]["id"]
        id_b = (
            supabase.table(enquiry_monthly_history_table)
            .insert({"year": 1901, "month": 3, "enquiry_count": 20})
            .execute()
        ).data[0]["id"]
        try:
            page = client.get("/enquiry-monthly-history/?limit=1&offset=0")
            assert page.status_code == 200
            body = page.json()
            assert body["total"] >= 2
            assert body["has_more"] is True

            full_limit = min(body["total"], 200)
            full_page = client.get(f"/enquiry-monthly-history/?limit={full_limit}&offset=0")
            assert full_page.status_code == 200
            full_body = full_page.json()
            assert len(full_body["items"]) == full_limit
            assert full_body["has_more"] is (full_body["total"] > full_limit)
        finally:
            supabase.table(enquiry_monthly_history_table).delete().eq("id", id_a).execute()
            supabase.table(enquiry_monthly_history_table).delete().eq("id", id_b).execute()


class TestGetEnquiryMonthlyHistory:
    def test_get_existing_returns_200(self, client, new_enquiry_monthly_history):
        response = client.get(f"/enquiry-monthly-history/{new_enquiry_monthly_history}")
        assert response.status_code == 200
        assert response.json()["id"] == new_enquiry_monthly_history

    def test_get_nonexistent_returns_404(self, client):
        response = client.get("/enquiry-monthly-history/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404


class TestCreateEnquiryMonthlyHistory:
    def test_create_then_delete(self, client, supabase, enquiry_monthly_history_table):
        payload = {"year": 1901, "month": 4, "enquiry_count": 77}
        created_id = None
        try:
            response = client.post("/enquiry-monthly-history/", json=payload)
            assert response.status_code == 201
            body = response.json()
            created_id = body["id"]
            assert body["year"] == payload["year"]
            assert body["month"] == payload["month"]
            assert body["enquiry_count"] == payload["enquiry_count"]
            # DB default applies when the request omits this.
            assert body["source"] == "synthetic"
        finally:
            if created_id:
                supabase.table(enquiry_monthly_history_table).delete().eq("id", created_id).execute()

    def test_create_duplicate_year_month_returns_400(
        self, client, supabase, enquiry_monthly_history_table, new_enquiry_monthly_history
    ):
        # new_enquiry_monthly_history already holds (1901, 1) - the UNIQUE
        # constraint should surface as a clean 400, not a 500.
        response = client.post(
            "/enquiry-monthly-history/", json={"year": 1901, "month": 1, "enquiry_count": 1}
        )
        assert response.status_code == 400


class TestUpdateEnquiryMonthlyHistory:
    def test_update_existing_returns_200(self, client, new_enquiry_monthly_history):
        response = client.patch(
            f"/enquiry-monthly-history/{new_enquiry_monthly_history}", json={"enquiry_count": 99}
        )
        assert response.status_code == 200
        assert response.json()["enquiry_count"] == 99
        assert response.json()["id"] == new_enquiry_monthly_history

    def test_update_nonexistent_returns_404(self, client):
        response = client.patch(
            "/enquiry-monthly-history/00000000-0000-0000-0000-000000000000",
            json={"enquiry_count": 1},
        )
        assert response.status_code == 404


class TestDeleteEnquiryMonthlyHistory:
    def test_delete_existing_returns_204(
        self, client, supabase, enquiry_monthly_history_table, admin_user_id
    ):
        insert_response = (
            supabase.table(enquiry_monthly_history_table)
            .insert({"year": 1901, "month": 5, "enquiry_count": 5})
            .execute()
        )
        row_id = insert_response.data[0]["id"]
        try:
            response = client.delete(f"/enquiry-monthly-history/{row_id}")
            assert response.status_code == 204
            follow_up = client.get(f"/enquiry-monthly-history/{row_id}")
            assert follow_up.status_code == 404

            # Soft delete, not hard delete — same check as every other module.
            row = (
                supabase.table(enquiry_monthly_history_table)
                .select("id,deleted_at,deleted_by")
                .eq("id", row_id)
                .single()
                .execute()
            ).data
            assert row is not None, "row was hard-deleted, not soft-deleted"
            assert row["deleted_at"] is not None
            assert row["deleted_by"] == admin_user_id
        finally:
            supabase.table(enquiry_monthly_history_table).delete().eq("id", row_id).execute()

    def test_delete_nonexistent_returns_404(self, client):
        response = client.delete("/enquiry-monthly-history/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404

    def test_delete_already_deleted_returns_404(
        self, client, supabase, enquiry_monthly_history_table
    ):
        insert_response = (
            supabase.table(enquiry_monthly_history_table)
            .insert({"year": 1901, "month": 6, "enquiry_count": 5})
            .execute()
        )
        row_id = insert_response.data[0]["id"]
        try:
            first = client.delete(f"/enquiry-monthly-history/{row_id}")
            assert first.status_code == 204
            second = client.delete(f"/enquiry-monthly-history/{row_id}")
            assert second.status_code == 404
        finally:
            supabase.table(enquiry_monthly_history_table).delete().eq("id", row_id).execute()
