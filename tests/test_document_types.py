"""Tests for the /document-types module (GET list, GET /{id}, POST, PATCH,
DELETE). Field names come directly from app/models/document_types.py
(DocumentTypeBase) and app/routers/document_types.py.

Unlike the prior seven modules, this table's delete mechanism is the
is_active column, not deleted_at/deleted_by - a deliberate judgment call
(see app/services/document_types_service.py's module docstring) since
document_types is reference/config data with no FKs pointing at it and
nothing personal in it. Tests here assert the row survives with
is_active=false, not that deleted_at/deleted_by got set.

Like fee_payments/scholarships/hostel_allotments/telecallers,
document_types has zero pre-existing seed rows on dev (confirmed live,
Sept 2026, before writing this module) - so there's no
"existing_document_type" fixture pulling a row that's always there.
Every test that needs one creates and cleans up its own instead. No FK
needed - document_types has no foreign keys.
"""
import pytest


@pytest.fixture
def new_document_type(supabase, document_types_table):
    """Creates one document_type row directly (bypassing the API, same
    as existing_lead/applicant/application do for setup), yields its id,
    and hard-deletes it afterward. Exists because this table has no
    pre-existing seed data to borrow."""
    insert_response = (
        supabase.table(document_types_table)
        .insert({"name": "Pytest Aadhar Card"})
        .execute()
    )
    document_type_id = insert_response.data[0]["id"]
    yield document_type_id
    supabase.table(document_types_table).delete().eq("id", document_type_id).execute()


class TestListDocumentTypes:
    def test_list_returns_200(self, client, new_document_type):
        response = client.get("/document-types/")
        assert response.status_code == 200
        body = response.json()
        assert isinstance(body["items"], list)
        assert isinstance(body["total"], int)
        assert body["limit"] == 50
        assert body["offset"] == 0
        assert isinstance(body["has_more"], bool)

    def test_pagination_limit_is_respected(self, client, new_document_type):
        response = client.get("/document-types/?limit=1&offset=0")
        assert response.status_code == 200
        body = response.json()
        assert len(body["items"]) <= 1
        assert body["limit"] == 1
        assert body["offset"] == 0

    def test_pagination_total_and_has_more_are_accurate(
        self, client, supabase, document_types_table
    ):
        # Deterministic regardless of whatever else is on dev: create two
        # known rows, then confirm `total` counts every matching row (not
        # just the page) and `has_more` reflects whether more rows exist
        # beyond the current page - not just that the array got sliced.
        id_a = (
            supabase.table(document_types_table)
            .insert({"name": "Pytest Pagination Document Type A"})
            .execute()
        ).data[0]["id"]
        id_b = (
            supabase.table(document_types_table)
            .insert({"name": "Pytest Pagination Document Type B"})
            .execute()
        ).data[0]["id"]
        try:
            page = client.get("/document-types/?limit=1&offset=0")
            assert page.status_code == 200
            body = page.json()
            assert body["total"] >= 2
            assert body["has_more"] is True

            full_limit = min(body["total"], 200)
            full_page = client.get(f"/document-types/?limit={full_limit}&offset=0")
            assert full_page.status_code == 200
            full_body = full_page.json()
            assert len(full_body["items"]) == full_body["total"]
            assert full_body["has_more"] is False
        finally:
            supabase.table(document_types_table).delete().eq("id", id_a).execute()
            supabase.table(document_types_table).delete().eq("id", id_b).execute()


class TestGetDocumentType:
    def test_get_existing_document_type_returns_200(self, client, new_document_type):
        response = client.get(f"/document-types/{new_document_type}")
        assert response.status_code == 200
        assert response.json()["id"] == new_document_type

    def test_get_nonexistent_document_type_returns_404(self, client):
        response = client.get("/document-types/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404


class TestCreateDocumentType:
    def test_create_document_type_then_delete(self, client, supabase, document_types_table):
        payload = {
            "name": "Pytest Transfer Certificate",
            "is_required": True,
            "sort_order": 5,
        }
        created_id = None
        try:
            response = client.post("/document-types/", json=payload)
            assert response.status_code == 201
            body = response.json()
            created_id = body["id"]
            assert body["name"] == payload["name"]
            assert body["is_required"] == payload["is_required"]
            assert body["sort_order"] == payload["sort_order"]
            # DB default applies when the request omits this.
            assert body["is_active"] is True
        finally:
            if created_id:
                supabase.table(document_types_table).delete().eq("id", created_id).execute()


class TestUpdateDocumentType:
    def test_update_existing_document_type_returns_200(self, client, new_document_type):
        response = client.patch(
            f"/document-types/{new_document_type}", json={"sort_order": 9}
        )
        assert response.status_code == 200
        assert response.json()["sort_order"] == 9
        assert response.json()["id"] == new_document_type

    def test_update_nonexistent_document_type_returns_404(self, client):
        response = client.patch(
            "/document-types/00000000-0000-0000-0000-000000000000",
            json={"sort_order": 9},
        )
        assert response.status_code == 404


class TestDeleteDocumentType:
    def test_delete_existing_document_type_returns_204(
        self, client, supabase, document_types_table
    ):
        insert_response = (
            supabase.table(document_types_table)
            .insert({"name": "Pytest Delete-Test Document Type"})
            .execute()
        )
        document_type_id = insert_response.data[0]["id"]
        try:
            response = client.delete(f"/document-types/{document_type_id}")
            assert response.status_code == 204
            follow_up = client.get(f"/document-types/{document_type_id}")
            assert follow_up.status_code == 404

            # is_active flip, not a hard delete - same "row survives" check
            # as every other module's soft delete, just a different column.
            row = (
                supabase.table(document_types_table)
                .select("id,is_active")
                .eq("id", document_type_id)
                .single()
                .execute()
            ).data
            assert row is not None, "row was hard-deleted, not deactivated"
            assert row["is_active"] is False
        finally:
            supabase.table(document_types_table).delete().eq("id", document_type_id).execute()

    def test_delete_nonexistent_document_type_returns_404(self, client):
        response = client.delete("/document-types/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404

    def test_delete_already_deleted_document_type_returns_404(
        self, client, supabase, document_types_table
    ):
        insert_response = (
            supabase.table(document_types_table)
            .insert({"name": "Pytest Double-Delete Document Type"})
            .execute()
        )
        document_type_id = insert_response.data[0]["id"]
        try:
            first = client.delete(f"/document-types/{document_type_id}")
            assert first.status_code == 204
            second = client.delete(f"/document-types/{document_type_id}")
            assert second.status_code == 404
        finally:
            supabase.table(document_types_table).delete().eq("id", document_type_id).execute()
