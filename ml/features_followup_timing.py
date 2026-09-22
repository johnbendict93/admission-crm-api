"""Feature definitions for roadmap module 14 - Optimal Follow-up Time
Predictor.

Predicts whether a follow-up call is likely to land a positive response,
purely from WHEN the call happens (hour of day) and WHO makes it
(called_by) - both columns live directly on followups (confirmed live via
app/models/followups.py, Sept 2026), so no join to leads is needed to
train this.

LABEL: followups.response is free text - no CHECK constraint, no fixed
dropdown (confirmed live). The fake seed data (scripts/seed_dev_fake_leads.py)
writes it from a small set of fixed call-outcome phrases, the same way many
real telecalling CRMs use a fixed "call disposition" convention in
practice. Rather than matching those exact phrases (which would only ever
work on this demo data), the label is a KEYWORD match on words like
"interested" / "positive" / "wants brochure" - it keeps working on any
future response text using similar words, not just this seed script's
wording. A true free-text sentiment model is module 19 (Phase 4, deferred -
that needs a much richer text bank than a handful of fixed phrases)."""
from typing import Optional

import pandas as pd

NUMERIC_FEATURES = ["hour"]
CATEGORICAL_FEATURES = ["called_by"]
FEATURE_COLUMNS = NUMERIC_FEATURES + CATEGORICAL_FEATURES

# Columns to SELECT from followups for training: features + the raw
# response text the label is derived from + id for traceability/ordering.
TRAINING_SELECT_COLUMNS = ["id", "call_time", "called_by", "response"]

# Call-center hours candidate window for the "what time should I call this
# lead" endpoint - matches the seed generator's CALL_HOURS (9am-8pm), a
# business convention, not a DB constraint.
CANDIDATE_HOURS = list(range(9, 21))

POSITIVE_KEYWORDS = ("interested", "positive", "wants brochure", "wants prospectus")


def make_label(response: Optional[str]) -> int:
    if not response:
        return 0
    text = str(response).lower()
    return 1 if any(k in text for k in POSITIVE_KEYWORDS) else 0


def extract_hour(call_time: Optional[str]) -> Optional[int]:
    """call_time is free text (confirmed live - not a native time type),
    written as 'HH:MM' by both the Streamlit app and this API's seed
    script, but nothing in the DB enforces that shape - parsed
    defensively rather than assumed."""
    if not call_time:
        return None
    try:
        hour = int(str(call_time).split(":")[0])
    except (ValueError, IndexError):
        return None
    return hour if 0 <= hour <= 23 else None


def rows_to_frame(rows: list[dict]) -> pd.DataFrame:
    """Raw DB rows (list of dicts) -> a DataFrame with exactly
    FEATURE_COLUMNS, in order, ready for the pipeline's ColumnTransformer.
    Missing called_by becomes "Unknown" (stable OneHotEncoder categories
    between training and inference, same convention as ml/features.py).
    Missing/unparseable hour is left as NaN - the pipeline's imputer
    handles it."""
    data = [{"hour": extract_hour(r.get("call_time")), "called_by": r.get("called_by")} for r in rows]
    df = pd.DataFrame(data, columns=FEATURE_COLUMNS)
    df["called_by"] = df["called_by"].fillna("Unknown").astype(str)
    return df
