"""Tests for GET /ml/telecallers/{telecaller_name}/ranked-leads (roadmap
module 21). Read-only, reuses module 13's trained conversion model. Field
names come from app/models/ml_lead_ranking.py.

Needs a telecaller name that actually has open (New/Contacted/Visited)
leads assigned, for a non-trivial happy path - a local, read-only fixture
finds one from the real seeded leads data rather than hardcoding one of
scripts/seed_dev_fake_leads.py's TELECALLERS names directly."""
import pytest


@pytest.fixture
def telecaller_with_open_leads(supabase, leads_table):
    response = (
        supabase.table(leads_table)
        .select("assigned_to")
        .not_.is_("assigned_to", "null")
        .in_("status", ["New", "Contacted", "Visited"])
        .is_("deleted_at", "null")
        .limit(1)
        .execute()
    )
    assert response.data, (
        "No leads with an open status and an assigned telecaller found - "
        "run scripts/seed_dev_fake_leads.py --apply first."
    )
    return response.data[0]["assigned_to"]


class TestRankedLeads:
    def test_telecaller_with_open_leads_returns_200_with_valid_shape(self, client, telecaller_with_open_leads):
        response = client.get(f"/ml/telecallers/{telecaller_with_open_leads}/ranked-leads")
        assert response.status_code == 200
        body = response.json()
        assert body["telecaller"] == telecaller_with_open_leads
        assert body["lead_count"] == len(body["ranked_leads"])
        assert body["lead_count"] > 0
        for lead in body["ranked_leads"]:
            assert isinstance(lead["lead_id"], str) and lead["lead_id"]
            assert isinstance(lead["name"], str) and lead["name"]
            assert isinstance(lead["phone"], str) and lead["phone"]
            assert 0.0 <= lead["predicted_conversion_probability"] <= 1.0
        assert isinstance(body["model_version"], str) and body["model_version"]

    def test_ranked_leads_sorted_best_first(self, client, telecaller_with_open_leads):
        response = client.get(f"/ml/telecallers/{telecaller_with_open_leads}/ranked-leads")
        assert response.status_code == 200
        probs = [lead["predicted_conversion_probability"] for lead in response.json()["ranked_leads"]]
        assert probs == sorted(probs, reverse=True)

    def test_unknown_telecaller_returns_200_with_empty_list(self, client):
        # assigned_to is free text, not a real FK to telecallers - an
        # unknown name is a valid (if empty) query, not a 404. See
        # app/routers/ml_lead_ranking.py's docstring.
        response = client.get("/ml/telecallers/Nonexistent Telecaller Name XYZ/ranked-leads")
        assert response.status_code == 200
        body = response.json()
        assert body["lead_count"] == 0
        assert body["ranked_leads"] == []
