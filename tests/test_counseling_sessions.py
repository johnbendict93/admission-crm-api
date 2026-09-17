"""Tests for the /counseling-sessions module (GET list, GET /{id}, POST,
PATCH, DELETE, soft-delete verification, CHECK constraint enforcement,
and the topics_discussed array field). Field names come directly from
app/models/counseling_sessions.py (CounselingSessionBase) and
app/routers/counseling_sessions.py.

Like followups/call_schedules/campus_visits, counseling_sessions has
zero pre-existing seed rows on dev (confirmed live, Sept 2026, before
writing this module) - so there's no "existing_counseling_session"
fixture pulling a row that's always there. Every test that needs one
creates and cleans up its own instead. This table is FK'd to applicants
(required) and users (required, as counselor_id) and applications
(nullable) - fixtures here use the existing_applicant/admin_user_id/
existing_application fixtures from conftest.py as FK targets.

Unlike followups/call_schedules/campus_visits/telecallers,
counseling_sessions has zero live Streamlit dependency (grepped
dce_crm - no reference to "counseling" anywhere), so there's no
cross-app visibility concern to account for here.
"""
import pytest


@pytest.fixture
def new_counseling_session(supabase, counseling_sessions_table, existing_applicant, admin_user_id):
    """Creates one counseling_sessions row directly (bypassing the API,
    same as existing_lead/applicant/application do for setup), yields
    its id, and hard-deletes it afterward. Exists because this table has
    no pre-existing seed data to borrow."""
    insert_response = (
        supabase.table(counseling_sessions_table)
        .insert(
            {
                "applicant_id": existing_applicant,
                "counselor_id": admin_user_id,
                "session_type": "Phone Call",
            }
        )
        .execute()
    )
    session_id = insert_response.data[0]["id"]
    yield session_id
    supabase.table(counseling_sessions_table).delete().eq("id", session_id).execute()


class TestListCounselingSessions:
    def test_list_returns_200(self, client, new_counseling_session):
        response = client.get("/counseling-sessions/")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_pagination_limit_is_respected(self, client, new_counseling_session):
        response = client.get("/counseling-sessions/?limit=1&offset=0")
        assert response.status_code == 200
        assert len(response.json()) <= 1


class TestGetCounselingSession:
    def test_get_existing_counseling_session_returns_200(self, client, new_counseling_session):
        response = client.get(f"/counseling-sessions/{new_counseling_session}")
        assert response.status_code == 200
        assert response.json()["id"] == new_counseling_session

    def test_get_nonexistent_counseling_session_returns_404(self, client):
        response = client.get("/counseling-sessions/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404


class TestCreateCounselingSession:
    def test_create_counseling_session_then_delete(
        self, client, supabase, counseling_sessions_table, existing_applicant, existing_application, admin_user_id
    ):
        payload = {
            "applicant_id": existing_applicant,
            "application_id": existing_application,
            "counselor_id": admin_user_id,
            "session_type": "Walk-in",
            "duration_mins": 25,
            "outcome": "Interested",
            "next_action": "Send fee structure",
            "notes": "Discussed B.Tech CSE options.",
            "mode": "In-Person",
        }
        created_id = None
        try:
            response = client.post("/counseling-sessions/", json=payload)
            assert response.status_code == 201
            body = response.json()
            created_id = body["id"]
            assert body["applicant_id"] == payload["applicant_id"]
            assert body["application_id"] == payload["application_id"]
            assert body["counselor_id"] == payload["counselor_id"]
            assert body["session_type"] == payload["session_type"]
            assert body["duration_mins"] == payload["duration_mins"]
            assert body["outcome"] == payload["outcome"]
            assert body["next_action"] == payload["next_action"]
            assert body["notes"] == payload["notes"]
            assert body["mode"] == payload["mode"]
            # DB defaults apply when the request omits these.
            assert body["session_date"] is not None
        finally:
            if created_id:
                supabase.table(counseling_sessions_table).delete().eq("id", created_id).execute()

    def test_topics_discussed_array_round_trips(
        self, client, supabase, counseling_sessions_table, existing_applicant, admin_user_id
    ):
        # topics_discussed is a native Postgres text[] - the first array
        # column in this project. Confirms the list survives the full
        # round trip: JSON body -> pydantic List[str] -> postgrest-py
        # insert -> Postgres text[] -> select back out as a JSON array,
        # not a stringified blob or a single concatenated value.
        topics = ["Fee structure", "Hostel availability", "Placement records"]
        payload = {
            "applicant_id": existing_applicant,
            "counselor_id": admin_user_id,
            "session_type": "Video Call",
            "topics_discussed": topics,
        }
        created_id = None
        try:
            create_response = client.post("/counseling-sessions/", json=payload)
            assert create_response.status_code == 201
            created_id = create_response.json()["id"]
            assert create_response.json()["topics_discussed"] == topics

            # Re-fetch via GET (a fresh SELECT, not just the insert's
            # RETURNING) to confirm the array survives a real read too.
            get_response = client.get(f"/counseling-sessions/{created_id}")
            assert get_response.status_code == 200
            assert get_response.json()["topics_discussed"] == topics
        finally:
            if created_id:
                supabase.table(counseling_sessions_table).delete().eq("id", created_id).execute()


class TestCounselingSessionErrorHandling:
    def test_invalid_session_type_returns_400(self, client, existing_applicant, admin_user_id):
        # counseling_sessions_session_type_check restricts session_type
        # to a fixed set of values. Violating it must surface as a
        # handled 400, never a raw 500, and must not create a row.
        payload = {
            "applicant_id": existing_applicant,
            "counselor_id": admin_user_id,
            "session_type": "Not-A-Real-Session-Type",
        }
        response = client.post("/counseling-sessions/", json=payload)
        assert response.status_code == 400
        assert response.status_code != 500

    def test_invalid_outcome_returns_400(self, client, existing_applicant, admin_user_id):
        # counseling_sessions_outcome_check restricts outcome to a fixed
        # set of values.
        payload = {
            "applicant_id": existing_applicant,
            "counselor_id": admin_user_id,
            "session_type": "Phone Call",
            "outcome": "Not-A-Real-Outcome",
        }
        response = client.post("/counseling-sessions/", json=payload)
        assert response.status_code == 400
        assert response.status_code != 500

    def test_invalid_mode_returns_400(self, client, existing_applicant, admin_user_id):
        # counseling_sessions_mode_check restricts mode to In-Person/Remote.
        payload = {
            "applicant_id": existing_applicant,
            "counselor_id": admin_user_id,
            "session_type": "Phone Call",
            "mode": "Hybrid",
        }
        response = client.post("/counseling-sessions/", json=payload)
        assert response.status_code == 400
        assert response.status_code != 500


class TestUpdateCounselingSession:
    def test_update_existing_counseling_session_returns_200(self, client, new_counseling_session):
        response = client.patch(
            f"/counseling-sessions/{new_counseling_session}", json={"outcome": "Confirmed"}
        )
        assert response.status_code == 200
        assert response.json()["outcome"] == "Confirmed"
        assert response.json()["id"] == new_counseling_session

    def test_update_nonexistent_counseling_session_returns_404(self, client):
        response = client.patch(
            "/counseling-sessions/00000000-0000-0000-0000-000000000000",
            json={"outcome": "Confirmed"},
        )
        assert response.status_code == 404

    def test_update_with_invalid_outcome_returns_400(self, client, new_counseling_session):
        # Violating counseling_sessions_outcome_check via PATCH must be a
        # handled 400, not a raw 500.
        response = client.patch(
            f"/counseling-sessions/{new_counseling_session}",
            json={"outcome": "Not-A-Real-Outcome"},
        )
        assert response.status_code == 400
        assert response.status_code != 500


class TestDeleteCounselingSession:
    def test_delete_existing_counseling_session_returns_204(
        self, client, supabase, counseling_sessions_table, existing_applicant, admin_user_id
    ):
        insert_response = (
            supabase.table(counseling_sessions_table)
            .insert(
                {
                    "applicant_id": existing_applicant,
                    "counselor_id": admin_user_id,
                    "session_type": "Email",
                }
            )
            .execute()
        )
        session_id = insert_response.data[0]["id"]
        try:
            response = client.delete(f"/counseling-sessions/{session_id}")
            assert response.status_code == 204
            follow_up = client.get(f"/counseling-sessions/{session_id}")
            assert follow_up.status_code == 404

            # Soft delete, not hard delete — same check as every other module.
            row = (
                supabase.table(counseling_sessions_table)
                .select("id,deleted_at,deleted_by")
                .eq("id", session_id)
                .single()
                .execute()
            ).data
            assert row is not None, "row was hard-deleted, not soft-deleted"
            assert row["deleted_at"] is not None
            assert row["deleted_by"] == admin_user_id
        finally:
            supabase.table(counseling_sessions_table).delete().eq("id", session_id).execute()

    def test_delete_nonexistent_counseling_session_returns_404(self, client):
        response = client.delete("/counseling-sessions/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404

    def test_delete_already_deleted_counseling_session_returns_404(
        self, client, supabase, counseling_sessions_table, existing_applicant, admin_user_id
    ):
        insert_response = (
            supabase.table(counseling_sessions_table)
            .insert(
                {
                    "applicant_id": existing_applicant,
                    "counselor_id": admin_user_id,
                    "session_type": "WhatsApp",
                }
            )
            .execute()
        )
        session_id = insert_response.data[0]["id"]
        try:
            first = client.delete(f"/counseling-sessions/{session_id}")
            assert first.status_code == 204
            second = client.delete(f"/counseling-sessions/{session_id}")
            assert second.status_code == 404
        finally:
            supabase.table(counseling_sessions_table).delete().eq("id", session_id).execute()
