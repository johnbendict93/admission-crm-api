"""Trains roadmap module 18 - Fee Default Risk Predictor.

Label: no matching fee_payments row exists for a fee_due_schedule row past
its due date (see ml/features_fee_default_risk.py's make_label). Reads dev
fee_due_schedule JOINed to applicants (for parent_occupation) with a LEFT
JOIN to fee_payments to determine the label, via DEV_DATABASE_URL (same
connection pattern as every other train_*.py script here). Trains the same
shared ml/pipeline.py pipeline (LogisticRegressionCV), evaluates with
5-fold stratified CV, and saves the fitted pipeline to
settings.FEE_DEFAULT_RISK_MODEL_PATH.

Run this yourself (needs your conda env / network - dev Supabase isn't
reachable from the cloud sandbox or the local Cowork shell):
    conda activate admission-crm-api
    python ml/train_fee_default_risk_model.py
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
from ml.features_fee_default_risk import CATEGORICAL_FEATURES, NUMERIC_FEATURES, make_label, rows_to_frame
from ml.pipeline import RANDOM_STATE, build_pipeline

CV_FOLDS = 5
CV_SCORING = ["roc_auc", "accuracy", "precision", "recall", "f1"]

# Explicit columns, not SELECT * - same convention as every other training
# script here. deleted_at filtered on fee_due_schedule/applicants/
# fee_payments (soft-deleted rows on any of the three must not leak into
# training). due_date < CURRENT_DATE: only rows whose payment outcome is
# already decided have a meaningful label - the seed generator guarantees
# this today, but the filter also protects this query once real, still-
# pending due dates exist in the table.
TRAINING_QUERY = """
    SELECT fds.amount_due, fds.due_date,
           p.parent_occupation,
           (fp.id IS NOT NULL) AS paid
    FROM public.fee_due_schedule fds
    JOIN public.applicants p ON p.id = fds.applicant_id
    LEFT JOIN public.fee_payments fp
        ON fp.applicant_id = fds.applicant_id
       AND fp.fee_component = fds.fee_component
       AND fp.academic_year = fds.academic_year
       AND fp.deleted_at IS NULL
    WHERE fds.deleted_at IS NULL AND p.deleted_at IS NULL AND fds.due_date < CURRENT_DATE
    ORDER BY fds.id;
"""  # amount_due/due_date/category deliberately NOT used as model features
# (see ml/features_fee_default_risk.py's docstring) - selected here only
# for the printed report / future re-evaluation.


def load_dev_fee_schedule() -> list[dict]:
    """ORDER BY fds.id for the same reproducibility reason as every other
    train_*.py script here: without it, row order (and therefore which
    rows land in which CV fold) isn't guaranteed stable between runs."""
    conn = psycopg2.connect(settings.DEV_DATABASE_URL)
    conn.set_session(readonly=True, autocommit=True)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(TRAINING_QUERY)
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()
    return rows


def main() -> None:
    if not settings.DEV_DATABASE_URL:
        print("DEV_DATABASE_URL not set - aborting.")
        sys.exit(1)

    rows = load_dev_fee_schedule()
    print(f"Loaded {len(rows)} fee_due_schedule rows (joined to applicant, matched against fee_payments) from dev.")

    X = rows_to_frame(rows)
    y = [make_label(r["paid"]) for r in rows]
    print(f"Label balance: {sum(y)} defaulted / {len(y) - sum(y)} paid")
    if sum(y) < CV_FOLDS or (len(y) - sum(y)) < CV_FOLDS:
        sys.exit(f"REFUSING: too few rows in one class ({sum(y)} defaulted / {len(y) - sum(y)} paid) "
                  f"for {CV_FOLDS}-fold stratified CV. Seed more fee_due_schedule rows first.")

    def make_this_pipeline():
        # cv_scoring="neg_log_loss", not the other modules' default
        # "roc_auc" - see ml/pipeline.py's build_pipeline() docstring
        # comment for why: with only one (categorical) feature and no
        # numeric features, "roc_auc" degenerately picks the strongest
        # regularization and collapses every prediction toward 0.5.
        return build_pipeline(numeric_features=NUMERIC_FEATURES, categorical_features=CATEGORICAL_FEATURES,
                               cv_scoring="neg_log_loss")

    skf = StratifiedKFold(n_splits=CV_FOLDS, shuffle=True, random_state=RANDOM_STATE)
    cv = cross_validate(make_this_pipeline(), X, y, cv=skf, scoring=CV_SCORING)

    metrics = {"n_rows": len(rows), "n_defaulted": sum(y), "cv_folds": CV_FOLDS}
    print(f"\n-- {CV_FOLDS}-fold cross-validated metrics (each row used as test exactly once) --")
    for name in CV_SCORING:
        scores = cv[f"test_{name}"]
        metrics[f"cv_{name}_mean"] = scores.mean()
        metrics[f"cv_{name}_std"] = scores.std()
        metrics[f"cv_{name}_folds"] = scores.tolist()
        print(f"{name:10}: mean={scores.mean():.3f}  std={scores.std():.3f}  folds={[round(s, 3) for s in scores]}")

    # Final deployed model: fit on ALL available data, same reasoning as
    # every other module here - CV above already gives the honest
    # generalization estimate.
    pipeline = make_this_pipeline()
    pipeline.fit(X, y)

    model_path = Path(__file__).resolve().parent.parent / settings.FEE_DEFAULT_RISK_MODEL_PATH
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, model_path)
    print(f"\nSaved model (trained on all {len(rows)} rows) to {model_path}")

    metrics_path = model_path.with_suffix(".metrics.json")
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, default=float)
    print(f"Saved metrics to {metrics_path}")


if __name__ == "__main__":
    main()
