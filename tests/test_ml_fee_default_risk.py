"""Tests for GET /ml/fee-due-schedule/{fee_due_schedule_id}/default-risk
(roadmap module 18). Read-only. Field names come from
app/models/ml_fee_default_risk.py; label text comes from
app/services/ml_fee_default_risk_service.py's predict_fee_default_risk().
Uses the existing_fee_due_schedule fixture (conftest.py) - real seeded
rows from scripts/seed_dev_fee_due_schedule.py, not created by this file."""


class TestFeeDefaultRisk:
    def test_existing_row_returns_200_with_valid_shape(self, client, existing_fee_due_schedule):
        response = client.get(f"/ml/fee-due-schedule/{existing_fee_due_schedule}/default-risk")
        assert response.status_code == 200
        body = response.json()
        assert body["fee_due_schedule_id"] == existing_fee_due_schedule
        assert isinstance(body["applicant_id"], str) and body["applicant_id"]
        assert isinstance(body["fee_component"], str) and body["fee_component"]
        assert body["amount_due"] >= 0
        assert isinstance(body["due_date"], str) and body["due_date"]
        assert 0.0 <= body["default_probability"] <= 1.0
        assert body["predicted_label"] in ("At risk of default", "Likely to pay")
        assert isinstance(body["model_version"], str) and body["model_version"]

    def test_predicted_label_matches_probability_threshold(self, client, existing_fee_due_schedule):
        response = client.get(f"/ml/fee-due-schedule/{existing_fee_due_schedule}/default-risk")
        assert response.status_code == 200
        body = response.json()
        expected = "At risk of default" if body["default_probability"] >= 0.5 else "Likely to pay"
        assert body["predicted_label"] == expected

    def test_nonexistent_row_returns_404(self, client):
        response = client.get("/ml/fee-due-schedule/00000000-0000-0000-0000-000000000000/default-risk")
        assert response.status_code == 404
