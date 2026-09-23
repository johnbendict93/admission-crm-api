"""Tests for GET /ml/leads/{lead_id}/best-followup-time (roadmap module
14). Read-only. Field names come from app/models/ml_followup_timing.py;
CANDIDATE_HOURS (9am-8pm, i.e. 9-20 inclusive) comes from
ml/features_followup_timing.py."""


class TestBestFollowupTime:
    def test_existing_lead_returns_200_with_valid_shape(self, client, existing_lead):
        response = client.get(f"/ml/leads/{existing_lead}/best-followup-time")
        assert response.status_code == 200
        body = response.json()
        assert body["lead_id"] == existing_lead
        assert 9 <= body["best_hour"] <= 20
        assert 0.0 <= body["best_hour_probability"] <= 1.0
        assert len(body["ranked_hours"]) == 12  # 9..20 inclusive
        for slot in body["ranked_hours"]:
            assert 9 <= slot["hour"] <= 20
            assert 0.0 <= slot["predicted_positive_probability"] <= 1.0
        assert isinstance(body["model_version"], str) and body["model_version"]

    def test_ranked_hours_sorted_best_first(self, client, existing_lead):
        response = client.get(f"/ml/leads/{existing_lead}/best-followup-time")
        assert response.status_code == 200
        probs = [slot["predicted_positive_probability"] for slot in response.json()["ranked_hours"]]
        assert probs == sorted(probs, reverse=True)

    def test_best_hour_matches_top_of_ranked_hours(self, client, existing_lead):
        response = client.get(f"/ml/leads/{existing_lead}/best-followup-time")
        assert response.status_code == 200
        body = response.json()
        assert body["best_hour"] == body["ranked_hours"][0]["hour"]
        assert body["best_hour_probability"] == body["ranked_hours"][0]["predicted_positive_probability"]

    def test_nonexistent_lead_returns_404(self, client):
        response = client.get("/ml/leads/00000000-0000-0000-0000-000000000000/best-followup-time")
        assert response.status_code == 404
