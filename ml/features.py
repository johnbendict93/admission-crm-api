"""Shared feature definitions for the leads-based ML modules (roadmap items
13-16 all reuse this - see next-module-brief.md's deferred-ML section).
Single source of truth for which lead columns are features, so training
and inference can never drift out of sync with each other.
"""
from typing import Any, Optional

import pandas as pd

# Matches columns confirmed live in app/models/leads.py - deliberately
# excludes PII (name, phone, email, parent_name, parent_phone) and
# id/status/created_at, which are identifiers or the label, not signal.
NUMERIC_FEATURES = ["marks", "score"]
BASE_CATEGORICAL_FEATURES = ["source", "district", "course_interest", "parent_occupation", "assigned_to"]

# Derived "telecaller x lead" interaction features (added Nov 2026). Without
# them a logistic model can only learn ONE fixed bonus per telecaller, the
# same for every lead - so "best telecaller for this lead" (module 17) and
# lead ranking always picked the same telecaller for everyone. Crossing the
# telecaller with the lead's course and parent occupation lets the model
# learn specialties ("B converts rural Mechanical leads well") while staying
# a plain, explainable logistic regression. Built in rows_to_frame, never
# stored in the DB.
INTERACTION_FEATURES = {
    "assigned_to_x_course": ("assigned_to", "course_interest"),
    "assigned_to_x_occupation": ("assigned_to", "parent_occupation"),
}
CATEGORICAL_FEATURES = BASE_CATEGORICAL_FEATURES + list(INTERACTION_FEATURES)
FEATURE_COLUMNS = NUMERIC_FEATURES + CATEGORICAL_FEATURES

# Columns to SELECT from the leads table for training: real DB columns only
# (the interaction features are derived) + the raw status the label is
# derived from + id for traceability.
TRAINING_SELECT_COLUMNS = NUMERIC_FEATURES + BASE_CATEGORICAL_FEATURES + ["id", "status"]

# Module 13's positive class. See RESOLVED_STATUSES/filter_resolved below
# for which rows this is actually evaluated against (revised 2026-09-22).
POSITIVE_STATUS = "Enrolled"


def make_label(status: Optional[str]) -> int:
    return 1 if status == POSITIVE_STATUS else 0


# Module 13, revised 2026-09-22: train only on RESOLVED leads (Enrolled or
# Lost). New/Contacted/Visited leads are excluded from training - the
# generator (scripts/seed_dev_fake_leads.py) rolls a separate
# age-based "resolved_prob" before ever checking "converts", so a lead
# that WOULD convert but is still recent often lands as New/Contacted/
# Visited rather than Enrolled. Folding those into the negative class
# mislabels genuine would-be conversions as losses - this is training-set
# curation, not something the model or extra features can fix.
NEGATIVE_STATUS = "Lost"
RESOLVED_STATUSES = {POSITIVE_STATUS, NEGATIVE_STATUS}

# Module 21 (Lead Ranking System) needs the complement: leads still being
# worked, with no outcome yet - exactly the ones a telecaller needs ranked.
# Matches the generator's actual status vocabulary (scripts/
# seed_dev_fake_leads.py: status is "Enrolled"/"Lost" once resolved, else
# one of these three) - hardcoded rather than "every status that isn't
# RESOLVED_STATUSES" because the DB has no CHECK constraint on leads.status,
# so an unexpected value should be excluded from ranking, not silently
# included as if it were open.
OPEN_STATUSES = {"New", "Contacted", "Visited"}


def filter_resolved(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in rows if r.get("status") in RESOLVED_STATUSES]


def rows_to_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Raw DB rows (list of dicts) -> a DataFrame with exactly
    FEATURE_COLUMNS, in order, ready for the pipeline's ColumnTransformer.
    Missing categorical values become the literal string "Unknown" (not
    NaN) so the fitted OneHotEncoder's categories stay stable between
    training and inference. Missing numeric values are left as NaN - the
    pipeline's own imputer handles those (see train_conversion_model.py)."""
    df = pd.DataFrame(rows)
    for col in NUMERIC_FEATURES + BASE_CATEGORICAL_FEATURES:
        if col not in df.columns:
            df[col] = None
    df = df[NUMERIC_FEATURES + BASE_CATEGORICAL_FEATURES].copy()
    for col in BASE_CATEGORICAL_FEATURES:
        df[col] = df[col].fillna("Unknown").astype(str)
    for name, (a, b) in INTERACTION_FEATURES.items():
        df[name] = df[a] + "|" + df[b]
    return df[FEATURE_COLUMNS]
