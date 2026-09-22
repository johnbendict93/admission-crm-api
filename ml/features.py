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
CATEGORICAL_FEATURES = ["source", "district", "course_interest", "parent_occupation", "assigned_to"]
FEATURE_COLUMNS = NUMERIC_FEATURES + CATEGORICAL_FEATURES

# Columns to SELECT from the leads table for training: features + the raw
# status the label is derived from + id for traceability.
TRAINING_SELECT_COLUMNS = FEATURE_COLUMNS + ["id", "status"]

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
    for col in FEATURE_COLUMNS:
        if col not in df.columns:
            df[col] = None
    df = df[FEATURE_COLUMNS].copy()
    for col in CATEGORICAL_FEATURES:
        df[col] = df[col].fillna("Unknown").astype(str)
    return df
