"""Tests for GET /ml/applications/{application_id}/dropout-risk (roadmap
module 16). Read-only. Field names come from app/models/ml_dropout_risk.py;
label text comes from app/services/ml_dropout_risk_service.py's
predict_dropout_risk()."""


class TestDropoutRisk:
    def test_existing_application_returns_200_with_valid_shape(self, client, existing_application):
        response = client.get(f"/ml/applications/{existing_application}/dropout-risk")
        assert response.status_code == 200
        body = response.json()
        assert body["application_id"] == existing_application
        assert isinstance(body["applicant_id"], str) and body["applicant_id"]
        assert 0.0 <= body["dropout_probability"] <= 1.0
        assert body["predicted_label"] in ("At risk of dropping out", "Likely to complete")
        assert isinstance(body["model_version"], str) and body["model_version"]

    def test_predicted_label_matches_probability_threshold(self, client, existing_application):
        response = client.get(f"/ml/applications/{existing_application}/dropout-risk")
        assert response.status_code == 200
        body = response.json()
        expected = "At risk of dropping out" if body["dropout_probability"] >= 0.5 else "Likely to complete"
        assert body["predicted_label"] == expected

    def test_nonexistent_application_returns_404(self, client):
        response = client.get("/ml/applications/00000000-0000-0000-0000-000000000000/dropout-risk")
        assert response.status_code == 404
