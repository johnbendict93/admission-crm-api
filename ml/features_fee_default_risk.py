"""Feature definitions for roadmap module 18 - Fee Default Risk Predictor.

Predicts whether an admitted applicant's fee instalment (fee_due_schedule,
migration 0019) will go unpaid past its due date, from signals known at the
time the schedule is set - never from anything only known once the payment
outcome is already decided (fee_payments itself, obviously, but also
nothing derived from it).

FEATURE LIST: parent_occupation only (CATEGORICAL_FEATURES). Audited before
choosing this (Golden Rule): applicants.annual_income - the obvious first
choice for a "can this family afford to pay" signal - is confirmed NEVER
populated by scripts/seed_dev_fake_leads.py (always NULL in dev), so it
would contribute nothing but noise, same as module 16's merit_rank/
category/programme/department lesson. amount_due and due_date are also
left out: scripts/seed_dev_fee_due_schedule.py generates both independently
of the default outcome (see that script's docstring - default risk is
driven solely by parent_occupation), so including them would be the same
mistake module 16 already made and had to walk back - features with no
real relationship to the label just add noise on a small table. category
(caste) is a plausible real-world fee-concession signal but was likewise
NOT wired into the seed generator's default logit, so it is left out for
the same reason; worth revisiting once real registrar data exists.

Needs a JOIN to applicants for parent_occupation (fee_due_schedule itself
has no applicant-profile columns). See
ml/train_fee_default_risk_model.py's load_dev_fee_schedule() for the query,
including how the label itself is computed (LEFT JOIN against
fee_payments - "does a matching payment exist" - rather than the seed
generator's own book-keeping, so the model is trained exactly the way it
will be evaluated against real future data)."""
from typing import Optional

import pandas as pd

NUMERIC_FEATURES: list[str] = []
CATEGORICAL_FEATURES = ["parent_occupation"]
FEATURE_COLUMNS = NUMERIC_FEATURES + CATEGORICAL_FEATURES


def make_label(paid: Optional[bool]) -> int:
    """1 = default risk realized (no matching payment found by due date),
    0 = paid. `paid` comes from the training/live query as
    "a matching fee_payments row exists" - see the module docstring."""
    return 0 if paid else 1


def rows_to_frame(rows: list[dict]) -> pd.DataFrame:
    """Raw DB rows (list of dicts) -> a DataFrame with exactly
    FEATURE_COLUMNS, in order. Missing categorical values become "Unknown"
    (stable OneHotEncoder categories between training and inference, same
    convention as ml/features.py and ml/features_dropout_risk.py)."""
    df = pd.DataFrame(rows)
    for col in FEATURE_COLUMNS:
        if col not in df.columns:
            df[col] = None
    df = df[FEATURE_COLUMNS].copy()
    for col in CATEGORICAL_FEATURES:
        df[col] = df[col].fillna("Unknown").astype(str)
    return df
