"""Tests for the /lookup-values module (GET list, GET /{id}, POST, PATCH,
DELETE). Field names come directly from app/models/lookup_values.py
(LookupValueBase) and app/routers/lookup_values.py.

Same is_active-instead-of-deleted_at judgment call as document_types -
see app/services/lookup_values_service.py's module docstring. Tests here
assert the row survives with is_active=false, not that
deleted_at/deleted_by got set.

Zero pre-existing seed rows on dev (confirmed live, Sept 2026, before
writing this module), so every test that needs a row creates and cleans
up its own. No FK needed - lookup_values has no foreign keys. UNIQUE
constraint is on (type, value) together, not on either column alone, so
test data can safely reuse a "type" across different tests as long as
the (type, value) pair is unique.
"""
import pytest


@pytest.fixture
def new_lookup_value(supabase, lookup_values_table):
    """Creates one lookup_value row directly (bypassing the API, same as
    existing_lead/applicant/application do for setup), yields its id, and
    hard-deletes it afterward. Exists because this table has no
    pre-existing seed data to borrow."""
    insert_response = (
        supabase.table(lookup_values_table)
        .insert({"type": "pytest_type", "value": "Pytest Value A"})
        .execute()
    )
    lookup_value_id = insert_response.data[0]["id"]
    yield lookup_value_id
    supabase.table(lookup_values_table).delete().eq("id", lookup_value_id).execute()


class TestListLookupValues:
    def test_list_returns_200(self, client, new_lookup_value):
        response = client.get("/lookup-values/")
        assert response.status_code == 200
        body = response.json()
        assert isinstance(body["items"], list)
        assert isinstance(body["total"], int)
        assert body["limit"] == 50
        assert body["offset"] == 0
        assert isinstance(body["has_more"], bool)

    def test_pagination_limit_is_respected(self, client, new_lookup_value):
        response = client.get("/lookup-values/?limit=1&offset=0")
        assert response.status_code == 200
        body = response.json()
        assert len(body["items"]) <= 1
        assert body["limit"] == 1
        assert body["offset"] == 0

    def test_pagination_total_and_has_more_are_accurate(
        self, client, supabase, lookup_values_table
    ):
        # Deterministic regardless of whatever else is on dev: create two
        # known rows, then confirm `total` counts every matching row (not
        # just the page) and `has_more` reflects whether more rows exist
        # beyond the current page - not just that the array got sliced.
        id_a = (
            supabase.table(lookup_values_table)
            .insert({"type": "pytest_pagination_type", "value": "Pagination Value A"})
            .execute()
        ).data[0]["id"]
        id_b = (
            supabase.table(lookup_values_table)
            .insert({"type": "pytest_pagination_type", "value": "Pagination Value B"})
            .execute()
        ).data[0]["id"]
        try:
            page = client.get("/lookup-values/?limit=1&offset=0")
            assert page.status_code == 200
            body = page.json()
            assert body["total"] >= 2
            assert body["has_more"] is True

            full_limit = min(body["total"], 200)
            full_page = client.get(f"/lookup-values/?limit={full_limit}&offset=0")
            assert full_page.status_code == 200
            full_body = full_page.json()
            assert len(full_body["items"]) == full_body["total"]
            assert full_body["has_more"] is False
        finally:
            supabase.table(lookup_values_table).delete().eq("id", id_a).execute()
            supabase.table(lookup_values_table).delete().eq("id", id_b).execute()


class TestGetLookupValue:
    def test_get_existing_lookup_value_returns_200(self, client, new_lookup_value):
        response = client.get(f"/lookup-values/{new_lookup_value}")
        assert response.status_code == 200
        assert response.json()["id"] == new_lookup_value

    def test_get_nonexistent_lookup_value_returns_404(self, client):
        response = client.get("/lookup-values/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404


class TestCreateLookupValue:
    def test_create_lookup_value_then_delete(self, client, supabase, lookup_values_table):
        payload = {
            "type": "pytest_type",
            "value": "Pytest Value B",
            "sort_order": 3,
        }
        created_id = None
        try:
            response = client.post("/lookup-values/", json=payload)
            assert response.status_code == 201
            body = response.json()
            created_id = body["id"]
            assert body["type"] == payload["type"]
            assert body["value"] == payload["value"]
            assert body["sort_order"] == payload["sort_order"]
            # DB default applies when the request omits this.
            assert body["is_active"] is True
        finally:
            if created_id:
                supabase.table(lookup_values_table).delete().eq("id", created_id).execute()


class TestUpdateLookupValue:
    def test_update_existing_lookup_value_returns_200(self, client, new_lookup_value):
        response = client.patch(
            f"/lookup-values/{new_lookup_value}", json={"sort_order": 9}
        )
        assert response.status_code == 200
        assert response.json()["sort_order"] == 9
        assert response.json()["id"] == new_lookup_value

    def test_update_nonexistent_lookup_value_returns_404(self, client):
        response = client.patch(
            "/lookup-values/00000000-0000-0000-0000-000000000000",
            json={"sort_order": 9},
        )
        assert response.status_code == 404


class TestDeleteLookupValue:
    def test_delete_existing_lookup_value_returns_204(
        self, client, supabase, lookup_values_table
    ):
        insert_response = (
            supabase.table(lookup_values_table)
            .insert({"type": "pytest_type", "value": "Pytest Delete-Test Value"})
            .execute()
        )
        lookup_value_id = insert_response.data[0]["id"]
        try:
            response = client.delete(f"/lookup-values/{lookup_value_id}")
            assert response.status_code == 204
            follow_up = client.get(f"/lookup-values/{lookup_value_id}")
            assert follow_up.status_code == 404

            # is_active flip, not a hard delete - same "row survives" check
            # as every other module's soft delete, just a different column.
            row = (
                supabase.table(lookup_values_table)
                .select("id,is_active")
                .eq("id", lookup_value_id)
                .single()
                .execute()
            ).data
            assert row is not None, "row was hard-deleted, not deactivated"
            assert row["is_active"] is False
        finally:
            supabase.table(lookup_values_table).delete().eq("id", lookup_value_id).execute()

    def test_delete_nonexistent_lookup_value_returns_404(self, client):
        response = client.delete("/lookup-values/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404

    def test_delete_already_deleted_lookup_value_returns_404(
        self, client, supabase, lookup_values_table
    ):
        insert_response = (
            supabase.table(lookup_values_table)
            .insert({"type": "pytest_type", "value": "Pytest Double-Delete Value"})
            .execute()
        )
        lookup_value_id = insert_response.data[0]["id"]
        try:
            first = client.delete(f"/lookup-values/{lookup_value_id}")
            assert first.status_code == 204
            second = client.delete(f"/lookup-values/{lookup_value_id}")
            assert second.status_code == 404
        finally:
            supabase.table(lookup_values_table).delete().eq("id", lookup_value_id).execute()
