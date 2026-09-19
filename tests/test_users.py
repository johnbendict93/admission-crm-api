"""Tests for the read-only /users module (GET list, GET /{id}). Field
names come from app/models/users.py (UserResponse) and
app/routers/users.py.

public.users is provisioned by Supabase Auth's on_auth_user_created
trigger, and the API has no way to create users (GET-only by design), so
these tests insert their own throwaway rows directly through the service
client - same "bypass the API for setup" pattern as the other modules -
and hard-delete them afterward. Dev's two real rows (the admin and viewer
test accounts from scripts/create_test_users.py) are only ever read.

users is not one of the fourteen tables in conftest's verify_db_untouched
sweep, so every fixture below cleans up after itself in a finally/yield
teardown and test_fixtures_leave_no_rows_behind checks that explicitly.
"""
import uuid

import pytest

SLIM_FIELDS = {"id", "full_name", "role", "department", "is_active"}
FORBIDDEN_FIELDS = {"email", "phone", "avatar_url", "created_at", "updated_at"}


def _insert_user(supabase, users_table, *, role, is_active, name):
    row = (
        supabase.table(users_table)
        .insert(
            {
                # .invalid is a reserved TLD - can never be a real mailbox.
                "email": f"pytest-{uuid.uuid4().hex[:12]}@pytest.invalid",
                "full_name": name,
                "role": role,
                "is_active": is_active,
                "department": "PytestDept",
            }
        )
        .execute()
    ).data[0]
    return row["id"]


@pytest.fixture
def inactive_user(supabase, users_table):
    user_id = _insert_user(supabase, users_table, role="staff", is_active=False, name="Pytest Inactive User")
    yield user_id
    supabase.table(users_table).delete().eq("id", user_id).execute()


@pytest.fixture
def extra_active_users(supabase, users_table):
    """Two more ACTIVE users (a counselor and a staff) so dev is guaranteed
    to hold at least four active users regardless of what else exists - the
    pagination and role-filter tests below then don't depend on how many
    real accounts happen to be there."""
    ids = [
        _insert_user(supabase, users_table, role="counselor", is_active=True, name="Pytest Active Counselor"),
        _insert_user(supabase, users_table, role="staff", is_active=True, name="Pytest Active Staff"),
    ]
    yield {"counselor": ids[0], "staff": ids[1]}
    for user_id in ids:
        supabase.table(users_table).delete().eq("id", user_id).execute()


def _ids(body):
    return {item["id"] for item in body["items"]}


def _all_users(client, **params):
    """Fetches every page so assertions can't be fooled by page boundaries."""
    items, offset = [], 0
    while True:
        response = client.get("/users/", params={**params, "limit": 200, "offset": offset})
        assert response.status_code == 200
        body = response.json()
        items.extend(body["items"])
        if not body["has_more"]:
            return items, body["total"]
        offset += len(body["items"])


class TestListUsers:
    def test_list_returns_200_with_standard_envelope(self, client):
        response = client.get("/users/")
        assert response.status_code == 200
        body = response.json()
        assert set(body) == {"items", "total", "limit", "offset", "has_more"}
        assert isinstance(body["items"], list)
        assert isinstance(body["total"], int)
        assert body["limit"] == 50
        assert body["offset"] == 0
        assert isinstance(body["has_more"], bool)

    def test_default_list_includes_real_active_users(self, client, admin_user_id, _viewer_login):
        items, total = _all_users(client)
        ids = {item["id"] for item in items}
        assert admin_user_id in ids
        assert _viewer_login["user"]["id"] in ids
        assert total == len(items)

    def test_default_list_only_returns_active_users(self, client, inactive_user):
        items, _ = _all_users(client)
        assert items, "expected at least the dev test accounts"
        assert all(item["is_active"] is True for item in items)

    def test_inactive_user_is_excluded_from_list_and_total(self, client, inactive_user, supabase, users_table):
        items, total = _all_users(client)
        assert inactive_user not in {item["id"] for item in items}
        # total must agree with the database's own count of active rows, not
        # merely with the number of items we happened to page through.
        db_active = supabase.table(users_table).select("id", count="exact").eq("is_active", True).execute().count
        assert total == db_active

    def test_response_items_have_only_the_slim_fields(self, client):
        items, _ = _all_users(client)
        for item in items:
            assert set(item) == SLIM_FIELDS
            assert not (set(item) & FORBIDDEN_FIELDS)

    def test_no_email_or_phone_anywhere_in_the_response_body(self, client, settings_test_admin_email):
        response = client.get("/users/")
        assert response.status_code == 200
        text = response.text.lower()
        assert settings_test_admin_email.lower() not in text
        assert "@" not in text, "no email address of any kind should appear in the /users response"
        assert "pytest.invalid" not in text

    def test_pagination_limit_and_offset_are_respected(self, client, extra_active_users):
        page1 = client.get("/users/?limit=2&offset=0").json()
        page2 = client.get("/users/?limit=2&offset=2").json()
        assert len(page1["items"]) == 2
        assert page1["limit"] == 2 and page1["offset"] == 0
        assert page1["has_more"] is True
        assert page2["offset"] == 2
        assert page2["items"], "with >=4 active users a second page must have rows"
        assert _ids(page1).isdisjoint(_ids(page2))

    def test_pagination_total_and_has_more_are_accurate(self, client, extra_active_users):
        first = client.get("/users/?limit=1&offset=0").json()
        assert first["total"] >= 4
        assert first["has_more"] is True
        full = client.get(f"/users/?limit={min(first['total'], 200)}&offset=0").json()
        assert len(full["items"]) == full["total"]
        assert full["has_more"] is False

    def test_ordering_is_by_full_name(self, client, extra_active_users):
        items, _ = _all_users(client)
        names = [item["full_name"] for item in items]
        # Postgres and Python can disagree on collation for exotic names, so
        # compare only the two known throwaway names, which sort predictably.
        assert names.index("Pytest Active Counselor") < names.index("Pytest Active Staff")

    def test_limit_validation(self, client):
        assert client.get("/users/?limit=0").status_code == 422
        assert client.get("/users/?limit=201").status_code == 422
        assert client.get("/users/?offset=-1").status_code == 422


class TestRoleFilter:
    def test_single_role_filter(self, client, extra_active_users, admin_user_id):
        items, total = _all_users(client, role="counselor")
        assert items
        assert all(item["role"] == "counselor" for item in items)
        assert extra_active_users["counselor"] in {item["id"] for item in items}
        assert admin_user_id not in {item["id"] for item in items}
        assert total == len(items)

    def test_repeated_role_params_are_multi_value(self, client, extra_active_users, admin_user_id, _viewer_login):
        items, total = _all_users(client, role=["admin", "counselor", "staff"])
        ids = {item["id"] for item in items}
        assert {item["role"] for item in items} <= {"admin", "counselor", "staff"}
        assert admin_user_id in ids
        assert extra_active_users["counselor"] in ids
        assert extra_active_users["staff"] in ids
        # This is exactly what the frontend's counselor picker asks for:
        # viewers must be excluded.
        assert _viewer_login["user"]["id"] not in ids
        assert total == len(items)

    def test_comma_separated_role_param_is_multi_value(self, client, extra_active_users, admin_user_id, _viewer_login):
        items, _ = _all_users(client, role="admin,counselor,staff")
        ids = {item["id"] for item in items}
        assert {item["role"] for item in items} <= {"admin", "counselor", "staff"}
        assert admin_user_id in ids and extra_active_users["staff"] in ids
        assert _viewer_login["user"]["id"] not in ids

    def test_comma_and_repeated_forms_are_equivalent(self, client, extra_active_users):
        comma, comma_total = _all_users(client, role="admin,staff")
        repeated, repeated_total = _all_users(client, role=["admin", "staff"])
        assert {i["id"] for i in comma} == {i["id"] for i in repeated}
        assert comma_total == repeated_total

    def test_whitespace_and_empty_segments_are_tolerated(self, client, extra_active_users):
        items, _ = _all_users(client, role=" counselor , ,")
        assert items and all(item["role"] == "counselor" for item in items)

    def test_blank_role_param_means_no_filter(self, client):
        unfiltered, unfiltered_total = _all_users(client)
        blank, blank_total = _all_users(client, role=",")
        assert blank_total == unfiltered_total

    def test_unknown_role_matches_nothing_and_is_not_an_error(self, client):
        response = client.get("/users/?role=definitely_not_a_role")
        assert response.status_code == 200
        body = response.json()
        assert body["items"] == [] and body["total"] == 0 and body["has_more"] is False

    def test_role_filter_still_excludes_inactive(self, client, inactive_user):
        items, _ = _all_users(client, role="staff")
        assert inactive_user not in {item["id"] for item in items}


class TestGetUser:
    def test_get_existing_user_returns_200_slim(self, client, admin_user_id):
        response = client.get(f"/users/{admin_user_id}")
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == admin_user_id
        assert body["role"] == "admin"
        assert set(body) == SLIM_FIELDS
        assert "@" not in response.text

    def test_get_nonexistent_user_returns_404(self, client):
        response = client.get("/users/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404

    def test_get_inactive_user_returns_404(self, client, inactive_user):
        assert client.get(f"/users/{inactive_user}").status_code == 404


class TestUsersAuth:
    def test_list_without_token_returns_401(self, client):
        response = client.get("/users/", headers={"Authorization": ""})
        assert response.status_code == 401
        assert response.status_code != 500

    def test_get_without_token_returns_401(self, client, admin_user_id):
        response = client.get(f"/users/{admin_user_id}", headers={"Authorization": ""})
        assert response.status_code == 401

    def test_garbage_token_returns_401(self, client):
        assert client.get("/users/", headers={"Authorization": "Bearer garbage.not.a.jwt"}).status_code == 401

    def test_viewer_role_can_read(self, viewer_client, admin_user_id):
        # Same gating as every other module's GETs: any authenticated,
        # active user may read; only writes need require_writer.
        assert viewer_client.get("/users/").status_code == 200
        assert viewer_client.get(f"/users/{admin_user_id}").status_code == 200

    def test_module_is_read_only(self, client, admin_user_id):
        assert client.post("/users/", json={"email": "x@example.com"}).status_code == 405
        assert client.patch(f"/users/{admin_user_id}", json={"role": "viewer"}).status_code == 405
        assert client.delete(f"/users/{admin_user_id}").status_code == 405


def test_fixtures_leave_no_rows_behind(supabase, users_table):
    leftovers = supabase.table(users_table).select("id").like("email", "pytest-%@pytest.invalid").execute().data
    assert leftovers == []
