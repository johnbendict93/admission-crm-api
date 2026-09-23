"""Feature definitions for roadmap module 16 - Dropout Risk at Admission
Stage.

Predicts whether an application will NOT be completed (application_stage
!= "Admitted") from academic/demographic signals available at application
time - never from anything only known once the outcome is already decided.

Deliberately EXCLUDES allotted_seat_type: confirmed live (app/models/
applications.py) and in the seed generator (scripts/seed_dev_fake_leads.py)
that this is only ever set once a seat is actually allotted - i.e. only
for Admitted applications. Including it would let the model "predict" the
label by checking whether it already knows the outcome (leakage), not by
learning anything about dropout risk. submitted_at/reviewed_at are
similarly outcome-adjacent (how far the paperwork got, not who the
applicant is) and are left out for the same reason.

FEATURE LIST (revised Sept 2026, first live retrain): started at 9
features (4 numeric + 5 categorical: category/lead_source/programme/
department added). Live dev data (178 applications - a genuinely small
table right now) gave 5-fold CV ROC-AUC 0.540 with std 0.149 - swinging
from 0.37 to 0.71 fold to fold, not a trustworthy number. Checked each
feature's actual contribution on the same data: merit_rank is a pure
rank-transform of cutoff_marks in this seed generator (identical AUC
whether either one is used alone - see scripts/seed_dev_fake_leads.py's
merit_rank assignment), so keeping both just duplicates one signal across
two columns; category/programme/department carry no real signal by
construction (the seed generator picks them independently of the
admitted/dropout outcome); lead_source measurably hurt (0.588 vs 0.629
without it) once combined with the numeric features, most likely because
its ~9 categories are too sparse on ~140 training rows per fold to
estimate reliably rather than genuinely uninformative. Trimming to the
4 features below recovered mean ROC-AUC to 0.657 with std 0.058 - both
better AND far more stable, on the exact same 178 rows. Worth
re-evaluating once there are enough applications for the dropped
features (lead_source especially) to be estimated reliably again.

Needs a JOIN to applicants (applications itself has no cutoff_marks/
twelfth_percentage/parent_occupation - those live on the applicant's
profile, confirmed live via app/models/applicants.py). See
ml/train_dropout_risk_model.py's load_dev_applications() for the query."""
from typing import Optional

import pandas as pd

NUMERIC_FEATURES = ["cutoff_marks", "twelfth_percentage", "pcm_marks"]
CATEGORICAL_FEATURES = ["parent_occupation"]
FEATURE_COLUMNS = NUMERIC_FEATURES + CATEGORICAL_FEATURES

POSITIVE_STAGE = "Admitted"  # completed the funnel - NOT a dropout


def make_label(application_stage: Optional[str]) -> int:
    """1 = dropout risk realized (did not complete the funnel), 0 = Admitted.
    Matches the funnel vocabulary designed in scripts/seed_dev_fake_leads.py
    (Draft/Documents Submitted/Fee Pending/Verified/Withdrawn all count as
    not-yet-completed; the DB has no CHECK constraint on this column, so
    any stage other than the literal "Admitted" is treated as not done)."""
    return 0 if application_stage == POSITIVE_STAGE else 1


def rows_to_frame(rows: list[dict]) -> pd.DataFrame:
    """Raw DB rows (list of dicts, from the applications JOIN applicants
    query) -> a DataFrame with exactly FEATURE_COLUMNS, in order. Missing
    categorical values become "Unknown" (stable OneHotEncoder categories
    between training and inference, same convention as ml/features.py).
    Missing numeric values are left as NaN - the pipeline's imputer
    handles those."""
    df = pd.DataFrame(rows)
    for col in FEATURE_COLUMNS:
        if col not in df.columns:
            df[col] = None
    df = df[FEATURE_COLUMNS].copy()
    for col in CATEGORICAL_FEATURES:
        df[col] = df[col].fillna("Unknown").astype(str)
    return df
