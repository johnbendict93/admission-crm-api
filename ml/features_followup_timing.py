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

# Revised Nov 2026. The first version used hour as a NUMERIC feature with
# called_by only, so a logistic model could only learn "later is better" (a
# straight line) - every lead got the same answer (8 PM). Now:
#   * hour is CATEGORICAL ("09".."20"), so each hour gets its own weight;
#   * parent_occupation comes from the lead (joined at training time), and
#     the hour x occupation cross lets the model learn that, e.g., farming
#     families pick up early while office workers pick up after 6 PM.
# No numeric features left, so training passes cv_scoring="neg_log_loss"
# (see ml/pipeline.py on why ROC-AUC degenerates for all-categorical models).
NUMERIC_FEATURES: list[str] = []
CATEGORICAL_FEATURES = ["hour", "called_by", "parent_occupation", "hour_x_occupation"]
FEATURE_COLUMNS = NUMERIC_FEATURES + CATEGORICAL_FEATURES

# Training query (ml/train_followup_timing_model.py) joins followups to
# leads for parent_occupation - these are the followups-side columns.
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


def _hour_label(hour) -> str:
    return "Unknown" if hour is None else f"{int(hour):02d}"


def build_frame(items: list[dict]) -> pd.DataFrame:
    """items: dicts with hour (int or None), called_by, parent_occupation.
    Shared by training (rows_to_frame) and inference (frame_for_lead) so
    the two can never drift apart."""
    df = pd.DataFrame(
        [{"hour": _hour_label(i.get("hour")),
          "called_by": i.get("called_by"),
          "parent_occupation": i.get("parent_occupation")} for i in items],
        columns=["hour", "called_by", "parent_occupation"],
    )
    for col in ("called_by", "parent_occupation"):
        df[col] = df[col].fillna("Unknown").astype(str)
    df["hour_x_occupation"] = df["hour"] + "|" + df["parent_occupation"]
    return df[FEATURE_COLUMNS]


def rows_to_frame(rows: list[dict]) -> pd.DataFrame:
    """Training rows (followups joined to leads.parent_occupation) ->
    DataFrame with exactly FEATURE_COLUMNS."""
    return build_frame([{"hour": extract_hour(r.get("call_time")),
                         "called_by": r.get("called_by"),
                         "parent_occupation": r.get("parent_occupation")} for r in rows])


def frame_for_lead(lead: dict) -> pd.DataFrame:
    """One row per CANDIDATE_HOURS for this lead (its telecaller + parent
    occupation) - what the best-time endpoint scores."""
    return build_frame([{"hour": h,
                         "called_by": lead.get("assigned_to"),
                         "parent_occupation": lead.get("parent_occupation")} for h in CANDIDATE_HOURS])
