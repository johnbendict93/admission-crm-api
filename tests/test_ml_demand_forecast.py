"""Tests for GET /ml/demand-forecast/{year}/{month} (roadmap module 20).
Read-only, no entity id - a pure function of the calendar date. Field
names come from app/models/ml_demand_forecast.py. BASE_YEAR (the router's
own `ge` path constraint) comes from ml/features_demand_forecast.py, not
hardcoded here - see that module's docstring for why."""
from ml.features_demand_forecast import BASE_YEAR


class TestDemandForecast:
    def test_valid_month_returns_200_with_valid_shape(self, client):
        response = client.get(f"/ml/demand-forecast/{BASE_YEAR + 2}/6")
        assert response.status_code == 200
        body = response.json()
        assert body["year"] == BASE_YEAR + 2
        assert body["month"] == 6
        assert body["predicted_enquiry_count"] >= 0.0
        assert isinstance(body["model_version"], str) and body["model_version"]

    def test_prediction_is_deterministic(self, client):
        first = client.get(f"/ml/demand-forecast/{BASE_YEAR + 2}/6").json()
        second = client.get(f"/ml/demand-forecast/{BASE_YEAR + 2}/6").json()
        assert first["predicted_enquiry_count"] == second["predicted_enquiry_count"]

    def test_every_month_of_a_year_returns_200(self, client):
        # Exercises all 12 months, including the month_sin/month_cos
        # wraparound at December -> January (see
        # ml/features_demand_forecast.py) - never a 500, always a
        # non-negative prediction.
        for month in range(1, 13):
            response = client.get(f"/ml/demand-forecast/{BASE_YEAR + 3}/{month}")
            assert response.status_code == 200
            assert response.json()["predicted_enquiry_count"] >= 0.0

    def test_year_before_base_year_returns_422(self, client):
        response = client.get(f"/ml/demand-forecast/{BASE_YEAR - 1}/6")
        assert response.status_code == 422

    def test_month_zero_returns_422(self, client):
        response = client.get(f"/ml/demand-forecast/{BASE_YEAR + 1}/0")
        assert response.status_code == 422

    def test_month_thirteen_returns_422(self, client):
        response = client.get(f"/ml/demand-forecast/{BASE_YEAR + 1}/13")
        assert response.status_code == 422
