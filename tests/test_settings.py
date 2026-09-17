"""Tests for the /settings module (GET list, GET /{id}, POST, PATCH,
DELETE, is_active-based delete verification, updated_at trigger
verification). Field names come directly from app/models/settings.py
(SettingBase) and app/routers/settings.py.

Like document_types/lookup_values, settings has zero pre-existing seed
rows on dev (confirmed live, Sept 2026, before writing this module) -
so there's no "existing_setting" fixture pulling a row that's always
there. Every test that needs one creates and cleans up its own instead,
same pattern as tests/test_document_types.py. No FK dependency - this
table stands alone.
"""
import pytest


@pytest.fixture
def new_setting(supabase, settings_table):
    """Creates one setting row directly (bypassing the API, same as
    existing_lead/applicant/application do for setup), yields its id,
    and hard-deletes it afterward. Exists because this table has no
    pre-existing seed data to borrow."""
    insert_response = (
        supabase.table(settings_table)
        .insert({"category": "pytest", "key": "list_test_key", "value": "list_test_value"})
        .execute()
    )
    setting_id = insert_response.data[0]["id"]
    yield setting_id
    supabase.table(settings_table).delete().eq("id", setting_id).execute()


class TestListSettings:
    def test_list_returns_200(self, client, new_setting):
        response = client.get("/settings/")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_pagination_limit_is_respected(self, client, new_setting):
        response = client.get("/settings/?limit=1&offset=0")
        assert response.status_code == 200
        assert len(response.json()) <= 1


class TestGetSetting:
    def test_get_existing_setting_returns_200(self, client, new_setting):
        response = client.get(f"/settings/{new_setting}")
        assert response.status_code == 200
        assert response.json()["id"] == new_setting

    def test_get_nonexistent_setting_returns_404(self, client):
        response = client.get("/settings/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404


class TestCreateSetting:
    def test_create_setting_then_delete(self, client, supabase, settings_table):
        payload = {
            "category": "pytest",
            "key": "create_test_key",
            "value": "create_test_value",
        }
        created_id = None
        try:
            response = client.post("/settings/", json=payload)
            assert response.status_code == 201
            body = response.json()
            created_id = body["id"]
            assert body["category"] == payload["category"]
            assert body["key"] == payload["key"]
            assert body["value"] == payload["value"]
            # DB default applies when the request omits this.
            assert body["is_active"] is True
        finally:
            if created_id:
                supabase.table(settings_table).delete().eq("id", created_id).execute()

    def test_create_duplicate_category_key_returns_400(
        self, client, supabase, settings_table, new_setting
    ):
        # new_setting already occupies ("pytest", "list_test_key") -
        # the live UNIQUE(category, key) constraint should reject a
        # second insert with the same pair.
        response = client.post(
            "/settings/",
            json={"category": "pytest", "key": "list_test_key", "value": "different_value"},
        )
        assert response.status_code == 400


class TestUpdateSetting:
    def test_update_existing_setting_returns_200(self, client, new_setting):
        response = client.patch(
            f"/settings/{new_setting}", json={"value": "updated_value"}
        )
        assert response.status_code == 200
        assert response.json()["value"] == "updated_value"
        assert response.json()["id"] == new_setting

    def test_update_nonexistent_setting_returns_404(self, client):
        response = client.patch(
            "/settings/00000000-0000-0000-0000-000000000000",
            json={"value": "updated_value"},
        )
        assert response.status_code == 404

    def test_update_bumps_updated_at_via_trigger(self, client, supabase, settings_table, new_setting):
        # Confirms migration 0011's trigger actually fires - not just
        # that the column exists.
        before = (
            supabase.table(settings_table)
            .select("updated_at")
            .eq("id", new_setting)
            .single()
            .execute()
        ).data["updated_at"]
        response = client.patch(f"/settings/{new_setting}", json={"value": "trigger_check"})
        assert response.status_code == 200
        after = response.json()["updated_at"]
        assert after != before, "updated_at did not change - trigger may not be attached"


class TestDeleteSetting:
    def test_delete_existing_setting_returns_204(
        self, client, supabase, settings_table
    ):
        insert_response = (
            supabase.table(settings_table)
            .insert({"category": "pytest", "key": "delete_test_key", "value": "delete_test_value"})
            .execute()
        )
        setting_id = insert_response.data[0]["id"]
        try:
            response = client.delete(f"/settings/{setting_id}")
            assert response.status_code == 204
            follow_up = client.get(f"/settings/{setting_id}")
            assert follow_up.status_code == 404

            # is_active flipped to false, not hard-deleted — same check
            # as every other is_active-based module.
            row = (
                supabase.table(settings_table)
                .select("id,is_active")
                .eq("id", setting_id)
                .single()
                .execute()
            ).data
            assert row is not None, "row was hard-deleted, not soft-deleted"
            assert row["is_active"] is False
        finally:
            supabase.table(settings_table).delete().eq("id", setting_id).execute()

    def test_delete_nonexistent_setting_returns_404(self, client):
        response = client.delete("/settings/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404

    def test_delete_already_deleted_setting_returns_404(
        self, client, supabase, settings_table
    ):
        insert_response = (
            supabase.table(settings_table)
            .insert({"category": "pytest", "key": "double_delete_test_key", "value": "x"})
            .execute()
        )
        setting_id = insert_response.data[0]["id"]
        try:
            first = client.delete(f"/settings/{setting_id}")
            assert first.status_code == 204
            second = client.delete(f"/settings/{setting_id}")
            assert second.status_code == 404
        finally:
            supabase.table(settings_table).delete().eq("id", setting_id).execute()
