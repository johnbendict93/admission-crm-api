"""Tests for GET /ml/leads/{lead_id}/conversion-prediction (roadmap module
13). Read-only endpoint - no fixture cleanup needed, verify_db_untouched
in conftest.py already guards the whole suite against accidental writes.
Field names come from app/models/ml_conversion.py; label text comes from
app/services/ml_conversion_service.py's predict_conversion()."""


class TestConversionPrediction:
    def test_existing_lead_returns_200_with_valid_shape(self, client, existing_lead):
        response = client.get(f"/ml/leads/{existing_lead}/conversion-prediction")
        assert response.status_code == 200
        body = response.json()
        assert body["lead_id"] == existing_lead
        assert 0.0 <= body["probability"] <= 1.0
        assert body["predicted_label"] in ("Likely to enroll", "Unlikely to enroll")
        assert isinstance(body["model_version"], str) and body["model_version"]

    def test_predicted_label_matches_probability_threshold(self, client, existing_lead):
        response = client.get(f"/ml/leads/{existing_lead}/conversion-prediction")
        assert response.status_code == 200
        body = response.json()
        expected = "Likely to enroll" if body["probability"] >= 0.5 else "Unlikely to enroll"
        assert body["predicted_label"] == expected

    def test_nonexistent_lead_returns_404(self, client):
        response = client.get("/ml/leads/00000000-0000-0000-0000-000000000000/conversion-prediction")
        assert response.status_code == 404
