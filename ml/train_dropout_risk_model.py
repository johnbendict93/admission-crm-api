"""Trains roadmap module 16 - Dropout Risk at Admission Stage.

Label: application_stage != "Admitted" (see ml/features_dropout_risk.py's
make_label). Reads dev applications JOINed to their applicant's profile via
DEV_DATABASE_URL (same connection pattern as ml/train_conversion_model.py
and ml/train_followup_timing_model.py) - applications alone doesn't carry
cutoff_marks/twelfth_percentage/parent_occupation/lead_source, those live
on applicants. Trains the same shared ml/pipeline.py pipeline
(LogisticRegressionCV), evaluates with 5-fold stratified CV, and saves the
fitted pipeline to settings.DROPOUT_RISK_MODEL_PATH.

Run this yourself (needs your conda env / network - dev Supabase isn't
reachable from the cloud sandbox or the local Cowork shell):
    conda activate admission-crm-api
    python ml/train_dropout_risk_model.py
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
from ml.features_dropout_risk import CATEGORICAL_FEATURES, NUMERIC_FEATURES, make_label, rows_to_frame
from ml.pipeline import RANDOM_STATE, build_pipeline

CV_FOLDS = 5
CV_SCORING = ["roc_auc", "accuracy", "precision", "recall", "f1"]

# a.* / p.* explicit columns, not SELECT * - same "no hardcoded schema
# guessing, always name the real columns" convention as every other
# training script here. deleted_at filtered on both sides: soft-deleted
# applications or applicants (neither currently used by this seed data,
# but a real column on both tables) must not leak into training.
TRAINING_QUERY = """
    SELECT a.application_stage,
           p.cutoff_marks, p.twelfth_percentage, p.pcm_marks, p.parent_occupation
    FROM public.applications a
    JOIN public.applicants p ON a.applicant_id = p.id
    WHERE a.deleted_at IS NULL AND p.deleted_at IS NULL
    ORDER BY a.id;
"""  # merit_rank/category/programme/department/lead_source dropped - see
# ml/features_dropout_risk.py's docstring for why each one was cut.


def load_dev_applications() -> list[dict]:
    """ORDER BY a.id for the same reproducibility reason as every other
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

    rows = load_dev_applications()
    print(f"Loaded {len(rows)} applications (joined to their applicant) from dev.")

    X = rows_to_frame(rows)
    y = [make_label(r["application_stage"]) for r in rows]
    print(f"Label balance: {sum(y)} did-not-complete / {len(y) - sum(y)} Admitted")
    if sum(y) < CV_FOLDS or (len(y) - sum(y)) < CV_FOLDS:
        sys.exit(f"REFUSING: too few rows in one class ({sum(y)} dropout / {len(y) - sum(y)} admitted) "
                  f"for {CV_FOLDS}-fold stratified CV. Seed more applications first.")

    def make_this_pipeline():
        return build_pipeline(numeric_features=NUMERIC_FEATURES, categorical_features=CATEGORICAL_FEATURES)

    skf = StratifiedKFold(n_splits=CV_FOLDS, shuffle=True, random_state=RANDOM_STATE)
    cv = cross_validate(make_this_pipeline(), X, y, cv=skf, scoring=CV_SCORING)

    metrics = {"n_rows": len(rows), "n_dropout": sum(y), "cv_folds": CV_FOLDS}
    print(f"\n-- {CV_FOLDS}-fold cross-validated metrics (each row used as test exactly once) --")
    for name in CV_SCORING:
        scores = cv[f"test_{name}"]
        metrics[f"cv_{name}_mean"] = scores.mean()
        metrics[f"cv_{name}_std"] = scores.std()
        metrics[f"cv_{name}_folds"] = scores.tolist()
        print(f"{name:10}: mean={scores.mean():.3f}  std={scores.std():.3f}  folds={[round(s, 3) for s in scores]}")

    # Final deployed model: fit on ALL available data, same reasoning as
    # modules 13 and 14 - CV above already gives the honest generalization
    # estimate.
    pipeline = make_this_pipeline()
    pipeline.fit(X, y)

    model_path = Path(__file__).resolve().parent.parent / settings.DROPOUT_RISK_MODEL_PATH
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, model_path)
    print(f"\nSaved model (trained on all {len(rows)} rows) to {model_path}")

    metrics_path = model_path.with_suffix(".metrics.json")
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, default=float)
    print(f"Saved metrics to {metrics_path}")


if __name__ == "__main__":
    main()
