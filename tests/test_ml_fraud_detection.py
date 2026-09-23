"""Tests for GET /ml/leads/{lead_id}/fraud-score (roadmap module 22).
Read-only. Field names come from app/models/ml_fraud_detection.py.

Deliberately does NOT depend on scripts/seed_dev_fraud_leads.py's ground
truth file (ml/eval/fraud_ground_truth.json) - that file is gitignored
(live DEV row ids, not part of the repo) and John may run --delete --apply
on those planted rows at any time. These tests only assert the response
SHAPE is valid for an ordinary lead (existing_lead - overwhelmingly likely
to be a real, non-planted lead given only ~28/534 are planted fraud), not
a specific anomaly verdict - see ml/features_fraud_detection.py's
docstring for why this module's ground truth stays eval-only, never a
test dependency either."""


class TestFraudScore:
    def test_existing_lead_returns_200_with_valid_shape(self, client, existing_lead):
        response = client.get(f"/ml/leads/{existing_lead}/fraud-score")
        assert response.status_code == 200
        body = response.json()
        assert body["lead_id"] == existing_lead
        assert isinstance(body["anomaly_score"], float)
        assert isinstance(body["is_anomalous"], bool)
        assert isinstance(body["model_version"], str) and body["model_version"]

    def test_nonexistent_lead_returns_404(self, client):
        response = client.get("/ml/leads/00000000-0000-0000-0000-000000000000/fraud-score")
        assert response.status_code == 404
