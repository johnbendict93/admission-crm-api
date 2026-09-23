"""Feature definitions for roadmap module 19 - NLP Call Sentiment Analyzer.

Predicts the sentiment (positive/neutral/negative) of a followup's free-
text notes. Unlike every other ML module here, the single feature IS free
text (followups.notes), not a set of numeric/categorical columns - see
ml/pipeline_text.py for why this needs a genuinely different pipeline
shape (TF-IDF, not ml/pipeline.py's shared ColumnTransformer).

LABEL: `response` is a short, fixed categorical phrase, not free text -
drawn from exactly RESPONSE_POS/NEU/NEG (scripts/seed_dev_fake_leads.py).
Because that set is small and exhaustive, which sentiment bucket a
followup belongs to is recoverable exactly from `response`, so no separate
label column or extra migration is needed. POSITIVE_RESPONSES/NEUTRAL_
RESPONSES/NEGATIVE_RESPONSES below MIRROR that script's RESPONSE_POS/NEU/
NEG - duplicated rather than imported, since the deployed API has no
reason to import from scripts/ (a dev-only tools directory); keep the two
in sync if that vocabulary ever changes.

NOTES TEXT: scripts/seed_dev_fake_leads.py's build_note() (added for this
module) and scripts/enrich_dev_followup_notes.py (backfills existing rows)
both generate notes tied to the SAME bucket that produced `response`, so
training on (notes -> bucket-derived label) is learning a real, if
synthetic, relationship - not a coincidence."""
from typing import Optional

POSITIVE_RESPONSES = ["Interested, will visit campus", "Interested, discussing with parent",
                       "Positive, asked about fee structure", "Wants brochure / prospectus sent"]
NEUTRAL_RESPONSES = ["Will call back later", "Asked to call after exams", "No response / voicemail", "Busy, call later"]
NEGATIVE_RESPONSES = ["Not interested", "Already joined elsewhere", "Wrong number", "Switched off"]

LABELS = ["negative", "neutral", "positive"]  # fixed, alphabetical order

RESPONSE_TO_LABEL: dict[str, str] = {}
for _r in POSITIVE_RESPONSES:
    RESPONSE_TO_LABEL[_r] = "positive"
for _r in NEUTRAL_RESPONSES:
    RESPONSE_TO_LABEL[_r] = "neutral"
for _r in NEGATIVE_RESPONSES:
    RESPONSE_TO_LABEL[_r] = "negative"


def make_label(response: Optional[str]) -> Optional[str]:
    """"positive"/"neutral"/"negative", or None if `response` isn't one of
    the known fixed phrases - such rows are skipped (at training time) or
    left unlabeled, never guessed at."""
    return RESPONSE_TO_LABEL.get(response)


def notes_to_text(rows: list[dict]) -> list[str]:
    """Raw DB rows -> the list of raw note strings TfidfVectorizer expects.
    Missing/empty notes become "" (an empty document, not dropped), so the
    row count always stays aligned with any parallel labels list."""
    return [(r.get("notes") or "") for r in rows]
