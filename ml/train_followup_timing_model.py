"""Trains roadmap module 14 - Optimal Follow-up Time Predictor.

Label: whether a follow-up call's response was positive, from a keyword
match on the response text (see ml/features_followup_timing.py's
POSITIVE_KEYWORDS/make_label for why keywords instead of exact phrases).
Reads all dev followups via DEV_DATABASE_URL (same connection pattern as
ml/train_conversion_model.py), trains a Logistic Regression pipeline
(same shared ml/pipeline.py as module 13 - LogisticRegressionCV picks its
own regularization strength), evaluates with 5-fold stratified
cross-validation (module 13 found a single train/test split unreliable at
this dataset size - see commit be2266d - so this module starts with CV
from day one instead of repeating that mistake), and saves the fitted
pipeline to settings.FOLLOWUP_TIMING_MODEL_PATH.

Run this yourself (needs your conda env / network - dev Supabase isn't
reachable from the cloud sandbox or the local Cowork shell):
    conda activate admission-crm-api
    python ml/train_followup_timing_model.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import joblib
import psycopg2
import psycopg2.extras
from sklearn.model_selection import StratifiedKFold, cross_validate

from app.core.config import settings
from ml.features_followup_timing import CATEGORICAL_FEATURES, NUMERIC_FEATURES, TRAINING_SELECT_COLUMNS, make_label, rows_to_frame
from ml.pipeline import RANDOM_STATE, build_pipeline

CV_FOLDS = 5
CV_SCORING = ["roc_auc", "accuracy", "precision", "recall", "f1"]


def load_dev_followups() -> list[dict]:
    """ORDER BY id for the same reproducibility reason as
    ml/train_conversion_model.py's load_dev_leads: without it, Postgres
    row order (and therefore which rows land in which CV fold) is not
    guaranteed stable between runs."""
    conn = psycopg2.connect(settings.DEV_DATABASE_URL)
    conn.set_session(readonly=True, autocommit=True)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cols = ", ".join(TRAINING_SELECT_COLUMNS)
    cur.execute(f"SELECT {cols} FROM public.followups ORDER BY id;")
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()
    return rows


def main() -> None:
    if not settings.DEV_DATABASE_URL:
        print("DEV_DATABASE_URL not set - aborting.")
        sys.exit(1)

    rows = load_dev_followups()
    print(f"Loaded {len(rows)} followups from dev.")

    X = rows_to_frame(rows)
    y = [make_label(r["response"]) for r in rows]
    print(f"Label balance: {sum(y)} positive-keyword responses / {len(y) - sum(y)} other")
    if sum(y) < CV_FOLDS or (len(y) - sum(y)) < CV_FOLDS:
        sys.exit(f"REFUSING: too few rows in one class ({sum(y)} positive / {len(y) - sum(y)} other) "
                  f"for {CV_FOLDS}-fold stratified CV. Seed more followups first.")

    def make_this_pipeline():
        return build_pipeline(numeric_features=NUMERIC_FEATURES, categorical_features=CATEGORICAL_FEATURES)

    skf = StratifiedKFold(n_splits=CV_FOLDS, shuffle=True, random_state=RANDOM_STATE)
    cv = cross_validate(make_this_pipeline(), X, y, cv=skf, scoring=CV_SCORING)

    metrics = {"n_rows": len(rows), "n_positive": sum(y), "cv_folds": CV_FOLDS}
    print(f"\n-- {CV_FOLDS}-fold cross-validated metrics (each row used as test exactly once) --")
    for name in CV_SCORING:
        scores = cv[f"test_{name}"]
        metrics[f"cv_{name}_mean"] = scores.mean()
        metrics[f"cv_{name}_std"] = scores.std()
        metrics[f"cv_{name}_folds"] = scores.tolist()
        print(f"{name:10}: mean={scores.mean():.3f}  std={scores.std():.3f}  folds={[round(s, 3) for s in scores]}")

    # Final deployed model: fit on ALL available data, same reasoning as
    # module 13 (train_conversion_model.py) - CV above already gives the
    # honest generalization estimate.
    pipeline = make_this_pipeline()
    pipeline.fit(X, y)

    model_path = Path(__file__).resolve().parent.parent / settings.FOLLOWUP_TIMING_MODEL_PATH
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, model_path)
    print(f"\nSaved model (trained on all {len(rows)} rows) to {model_path}")

    metrics_path = model_path.with_suffix(".metrics.json")
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, default=float)
    print(f"Saved metrics to {metrics_path}")


if __name__ == "__main__":
    main()
