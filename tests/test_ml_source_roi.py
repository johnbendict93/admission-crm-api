"""Tests for GET /ml/source-performance (roadmap module 15). Read-only,
pure aggregation over the live leads table - no trained model, no entity
id. Field names come from app/models/ml_source_roi.py."""


class TestSourcePerformance:
    def test_returns_200_with_valid_shape(self, client):
        response = client.get("/ml/source-performance")
        assert response.status_code == 200
        body = response.json()
        assert isinstance(body["note"], str) and body["note"]
        assert isinstance(body["sources"], list) and body["sources"]  # ~500 seeded leads exist

        for s in body["sources"]:
            assert isinstance(s["source"], str) and s["source"]
            assert s["total_leads"] >= 0
            assert s["enrolled_count"] >= 0
            assert s["lost_count"] >= 0
            assert s["unresolved_count"] >= 0
            assert s["enrolled_count"] + s["lost_count"] + s["unresolved_count"] == s["total_leads"]
            assert 0.0 <= s["overall_conversion_rate"] <= 1.0
            if s["resolved_conversion_rate"] is not None:
                assert 0.0 <= s["resolved_conversion_rate"] <= 1.0
            assert isinstance(s["low_sample"], bool)

    def test_sorted_by_resolved_conversion_rate_desc(self, client):
        # Per app/routers/ml_source_roi.py's docstring: sorted by
        # resolved_conversion_rate, unresolved-only sources (None) last.
        response = client.get("/ml/source-performance")
        assert response.status_code == 200
        rates = [s["resolved_conversion_rate"] for s in response.json()["sources"]]
        non_null = [r for r in rates if r is not None]
        assert non_null == sorted(non_null, reverse=True)
        # Any None entries must all trail the non-null ones.
        first_none_index = next((i for i, r in enumerate(rates) if r is None), len(rates))
        assert all(r is None for r in rates[first_none_index:])
