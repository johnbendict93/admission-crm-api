"""Tests for the /fee-payments module (GET list, GET /{id}, POST, PATCH,
DELETE, soft-delete verification). Field names come directly from
app/models/fee_payments.py (FeePaymentBase) and app/routers/fee_payments.py.

Unlike leads/applicants/applications, fee_payments has zero pre-existing
seed rows on dev (confirmed live, Sept 2026, before writing this module) -
so there's no "existing_fee_payment" fixture pulling a row that's always
there. Every test that needs one creates and cleans up its own instead,
the same way the other modules' create/update/delete tests already do for
rows they add themselves.
"""
import pytest


@pytest.fixture
def new_fee_payment(supabase, fee_payments_table, existing_applicant):
    """Creates one fee_payment row directly (bypassing the API, same as
    existing_lead/applicant/application do for setup), yields its id, and
    hard-deletes it afterward. Exists because this table has no
    pre-existing seed data to borrow, unlike the other three."""
    insert_response = (
        supabase.table(fee_payments_table)
        .insert(
            {
                "applicant_id": existing_applicant,
                "fee_component": "Tuition Fee",
                "amount": 5000,
                "payment_mode": "Cash",
            }
        )
        .execute()
    )
    fee_payment_id = insert_response.data[0]["id"]
    yield fee_payment_id
    supabase.table(fee_payments_table).delete().eq("id", fee_payment_id).execute()


class TestListFeePayments:
    def test_list_returns_200(self, client, new_fee_payment):
        response = client.get("/fee-payments/")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_pagination_limit_is_respected(self, client, new_fee_payment):
        response = client.get("/fee-payments/?limit=1&offset=0")
        assert response.status_code == 200
        assert len(response.json()) <= 1


class TestGetFeePayment:
    def test_get_existing_fee_payment_returns_200(self, client, new_fee_payment):
        response = client.get(f"/fee-payments/{new_fee_payment}")
        assert response.status_code == 200
        assert response.json()["id"] == new_fee_payment

    def test_get_nonexistent_fee_payment_returns_404(self, client):
        response = client.get("/fee-payments/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404


class TestCreateFeePayment:
    def test_create_fee_payment_then_delete(
        self, client, supabase, fee_payments_table, existing_applicant
    ):
        payload = {
            "applicant_id": existing_applicant,
            "fee_component": "Hostel Fee",
            "amount": 15000.50,
            "payment_mode": "UPI",
            "receipt_no": "PYTEST-0001",
        }
        created_id = None
        try:
            response = client.post("/fee-payments/", json=payload)
            assert response.status_code == 201
            body = response.json()
            created_id = body["id"]
            assert body["applicant_id"] == payload["applicant_id"]
            assert body["fee_component"] == payload["fee_component"]
            assert body["amount"] == payload["amount"]
            assert body["payment_mode"] == payload["payment_mode"]
            assert body["receipt_no"] == payload["receipt_no"]
            # DB defaults apply when the request omits these.
            assert body["payment_date"] is not None
            assert body["academic_year"] == "2026-27"
        finally:
            if created_id:
                supabase.table(fee_payments_table).delete().eq("id", created_id).execute()


class TestUpdateFeePayment:
    def test_update_existing_fee_payment_returns_200(self, client, new_fee_payment):
        response = client.patch(
            f"/fee-payments/{new_fee_payment}", json={"remarks": "Pytest updated remark"}
        )
        assert response.status_code == 200
        assert response.json()["remarks"] == "Pytest updated remark"
        assert response.json()["id"] == new_fee_payment

    def test_update_nonexistent_fee_payment_returns_404(self, client):
        response = client.patch(
            "/fee-payments/00000000-0000-0000-0000-000000000000",
            json={"remarks": "does not matter"},
        )
        assert response.status_code == 404


class TestDeleteFeePayment:
    def test_delete_existing_fee_payment_returns_204(
        self, client, supabase, fee_payments_table, existing_applicant, admin_user_id
    ):
        insert_response = (
            supabase.table(fee_payments_table)
            .insert(
                {
                    "applicant_id": existing_applicant,
                    "fee_component": "Exam Fee",
                    "amount": 500,
                    "payment_mode": "Cash",
                }
            )
            .execute()
        )
        fee_payment_id = insert_response.data[0]["id"]
        try:
            response = client.delete(f"/fee-payments/{fee_payment_id}")
            assert response.status_code == 204
            follow_up = client.get(f"/fee-payments/{fee_payment_id}")
            assert follow_up.status_code == 404

            # Soft delete, not hard delete — same check as leads/applicants/applications.
            row = (
                supabase.table(fee_payments_table)
                .select("id,deleted_at,deleted_by")
                .eq("id", fee_payment_id)
                .single()
                .execute()
            ).data
            assert row is not None, "row was hard-deleted, not soft-deleted"
            assert row["deleted_at"] is not None
            assert row["deleted_by"] == admin_user_id
        finally:
            supabase.table(fee_payments_table).delete().eq("id", fee_payment_id).execute()

    def test_delete_nonexistent_fee_payment_returns_404(self, client):
        response = client.delete("/fee-payments/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404

    def test_delete_already_deleted_fee_payment_returns_404(
        self, client, supabase, fee_payments_table, existing_applicant
    ):
        insert_response = (
            supabase.table(fee_payments_table)
            .insert(
                {
                    "applicant_id": existing_applicant,
                    "fee_component": "Lab Fee",
                    "amount": 1000,
                    "payment_mode": "Card",
                }
            )
            .execute()
        )
        fee_payment_id = insert_response.data[0]["id"]
        try:
            first = client.delete(f"/fee-payments/{fee_payment_id}")
            assert first.status_code == 204
            second = client.delete(f"/fee-payments/{fee_payment_id}")
            assert second.status_code == 404
        finally:
            supabase.table(fee_payments_table).delete().eq("id", fee_payment_id).execute()
