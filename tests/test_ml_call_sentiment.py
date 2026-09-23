"""Tests for GET /ml/followups/{followup_id}/sentiment (roadmap module 19).
Read-only. Field names come from app/models/ml_call_sentiment.py; the 3
label strings ("positive"/"neutral"/"negative") come from
ml/features_call_sentiment.py's LABELS.

Needs a followup with real, non-empty `notes` text - a freshly-created
blank test row would have nothing for the model to score. Uses a local,
read-only fixture (not conftest.py - only this file needs it) borrowing
one of the ~1580 real seeded followups with notes already in dev
(scripts/seed_dev_fake_leads.py's build_note(), enriched further by
scripts/enrich_dev_followup_notes.py for module 19)."""
import pytest


@pytest.fixture
def existing_followup_with_notes(supabase, followups_table):
    response = (
        supabase.table(followups_table)
        .select("id")
        .not_.is_("notes", "null")
        .neq("notes", "")
        .is_("deleted_at", "null")
        .limit(1)
        .execute()
    )
    assert response.data, (
        "No followups with notes found - run scripts/seed_dev_fake_leads.py "
        "--apply first (Phase 1 seed data includes followups.notes)."
    )
    return response.data[0]["id"]


class TestCallSentiment:
    def test_existing_followup_returns_200_with_valid_shape(self, client, existing_followup_with_notes):
        response = client.get(f"/ml/followups/{existing_followup_with_notes}/sentiment")
        assert response.status_code == 200
        body = response.json()
        assert body["followup_id"] == existing_followup_with_notes
        assert isinstance(body["notes"], str) and body["notes"]
        assert body["predicted_sentiment"] in ("positive", "neutral", "negative")
        assert isinstance(body["model_version"], str) and body["model_version"]

        assert len(body["scores"]) == 3
        labels = {s["label"] for s in body["scores"]}
        assert labels == {"positive", "neutral", "negative"}
        total_probability = sum(s["probability"] for s in body["scores"])
        assert abs(total_probability - 1.0) < 1e-3
        for s in body["scores"]:
            assert 0.0 <= s["probability"] <= 1.0

    def test_predicted_sentiment_is_the_highest_scoring_label(self, client, existing_followup_with_notes):
        response = client.get(f"/ml/followups/{existing_followup_with_notes}/sentiment")
        assert response.status_code == 200
        body = response.json()
        top = max(body["scores"], key=lambda s: s["probability"])
        assert top["label"] == body["predicted_sentiment"]

    def test_nonexistent_followup_returns_404(self, client):
        response = client.get("/ml/followups/00000000-0000-0000-0000-000000000000/sentiment")
        assert response.status_code == 404
