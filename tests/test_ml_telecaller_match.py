"""Tests for GET /ml/leads/{lead_id}/best-telecaller (roadmap module 17).
Read-only, reuses module 13's trained conversion model. Field names come
from app/models/ml_telecaller_match.py."""


class TestBestTelecaller:
    def test_existing_lead_returns_200_with_valid_shape(self, client, existing_lead):
        response = client.get(f"/ml/leads/{existing_lead}/best-telecaller")
        assert response.status_code == 200
        body = response.json()
        assert body["lead_id"] == existing_lead
        assert isinstance(body["best_telecaller"], str) and body["best_telecaller"]
        assert 0.0 <= body["best_telecaller_probability"] <= 1.0
        assert isinstance(body["ranked_telecallers"], list) and body["ranked_telecallers"]  # 4 active telecallers seeded
        for entry in body["ranked_telecallers"]:
            assert isinstance(entry["telecaller"], str) and entry["telecaller"]
            assert 0.0 <= entry["predicted_conversion_probability"] <= 1.0
        assert isinstance(body["model_version"], str) and body["model_version"]

    def test_ranked_telecallers_sorted_best_first(self, client, existing_lead):
        response = client.get(f"/ml/leads/{existing_lead}/best-telecaller")
        assert response.status_code == 200
        probs = [e["predicted_conversion_probability"] for e in response.json()["ranked_telecallers"]]
        assert probs == sorted(probs, reverse=True)

    def test_best_telecaller_matches_top_of_ranked_list(self, client, existing_lead):
        response = client.get(f"/ml/leads/{existing_lead}/best-telecaller")
        assert response.status_code == 200
        body = response.json()
        assert body["best_telecaller"] == body["ranked_telecallers"][0]["telecaller"]
        assert body["best_telecaller_probability"] == body["ranked_telecallers"][0]["predicted_conversion_probability"]

    def test_nonexistent_lead_returns_404(self, client):
        response = client.get("/ml/leads/00000000-0000-0000-0000-000000000000/best-telecaller")
        assert response.status_code == 404
