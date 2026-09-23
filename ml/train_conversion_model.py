"""Trains roadmap module 13 - Admission Conversion Predictor.

Label: status == 'Enrolled' vs everything else (confirmed with John,
2026-09-22 - see ml/features.py POSITIVE_STATUS). Reads all dev leads via
DEV_DATABASE_URL (same connection pattern as the repo's check_*.py audit
scripts) and trains a Logistic Regression pipeline (class_weight='balanced' -
positive rate is ~20%; LogisticRegressionCV picks its own regularization
strength, see ml/pipeline.py).

EVALUATION (revised 2026-09-22, see commit after fb90f75): this used to
report a single held-out 80/20 split. With only ~99 positive (Enrolled)
rows total, that single split's ROC-AUC swung from ~0.39 to ~0.68 purely
from which ~20 positives happened to land in the test 20% - confirmed by
rerunning the same model on the same data across 10 different splits
(mean 0.537, std 0.087, range 0.39-0.68). That is not a trustworthy number
to quote, to John or to a buyer. Instead this now reports 5-fold stratified
cross-validation (every row used as test exactly once, mean +/- std) as the
real performance estimate, and fits the FINAL deployed model on ALL rows
(not just 80% of them) - once CV has already given an honest generalization
estimate, holding out a test set for the deployed model just wastes data.

Run this yourself (needs your conda env / network - dev Supabase isn't
reachable from the cloud sandbox or the local Cowork shell):
    conda activate admission-crm-api
    python ml/train_conversion_model.py
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
from ml.features import TRAINING_SELECT_COLUMNS, make_label, rows_to_frame
from ml.pipeline import RANDOM_STATE, build_pipeline

CV_FOLDS = 5
CV_SCORING = ["roc_auc", "accuracy", "precision", "recall", "f1"]


def load_dev_leads() -> list[dict]:
    """ORDER BY id: without an explicit order, Postgres can return rows in a
    different physical order between runs even when nothing changed, which
    would silently change which rows land in which CV fold - making metrics
    non-reproducible run to run for reasons that have nothing to do with the
    model. Ordering by id fixes that.

    WHERE email NOT LIKE 'fraud.%' (added for module 22): this query used
    to have no filter at all - it trained on every row in the table.
    scripts/seed_dev_fraud_leads.py plants deliberately-weird leads
    (duplicate phones, mismatched district/school, implausible marks/score)
    for module 22's anomaly detector to be evaluated against - without this
    filter, module 13's conversion model would quietly absorb those rows
    as ordinary negative examples too. Every planted fraud lead's email
    starts with "fraud." (see that script's docstring) so this filter
    reliably excludes exactly those rows and nothing else."""
    conn = psycopg2.connect(settings.DEV_DATABASE_URL)
    conn.set_session(readonly=True, autocommit=True)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cols = ", ".join(TRAINING_SELECT_COLUMNS)
    cur.execute(f"SELECT {cols} FROM public.leads WHERE email NOT LIKE 'fraud.%' ORDER BY id;")
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()
    return rows


def main() -> None:
    if not settings.DEV_DATABASE_URL:
        print("DEV_DATABASE_URL not set - aborting.")
        sys.exit(1)

    rows = load_dev_leads()
    print(f"Loaded {len(rows)} leads from dev.")
    # Label = Enrolled vs everything else (all leads). 5-fold CV
    # (ml/compare_label_definitions.py, 2026-09-22) showed "Enrolled vs Lost
    # only" performs statistically the same (mean AUC 0.648 vs 0.659) but
    # with ~3x the variance from having fewer rows (392 vs 507) - so the
    # full dataset wins on stability for no cost in accuracy.

    X = rows_to_frame(rows)
    y = [make_label(r["status"]) for r in rows]
    print(f"Label balance: {sum(y)} Enrolled / {len(y) - sum(y)} other")

    skf = StratifiedKFold(n_splits=CV_FOLDS, shuffle=True, random_state=RANDOM_STATE)
    cv = cross_validate(build_pipeline(), X, y, cv=skf, scoring=CV_SCORING)

    metrics = {"n_rows": len(rows), "n_positive": sum(y), "cv_folds": CV_FOLDS}
    print(f"\n-- {CV_FOLDS}-fold cross-validated metrics (each row used as test exactly once) --")
    for name in CV_SCORING:
        scores = cv[f"test_{name}"]
        metrics[f"cv_{name}_mean"] = scores.mean()
        metrics[f"cv_{name}_std"] = scores.std()
        metrics[f"cv_{name}_folds"] = scores.tolist()
        print(f"{name:10}: mean={scores.mean():.3f}  std={scores.std():.3f}  folds={[round(s, 3) for s in scores]}")

    # Final deployed model: fit on ALL available data. CV above already gave
    # the honest out-of-sample estimate; the model that actually serves
    # predictions should use every row it can.
    pipeline = build_pipeline()
    pipeline.fit(X, y)

    model_path = Path(__file__).resolve().parent.parent / settings.CONVERSION_MODEL_PATH
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, model_path)
    print(f"\nSaved model (trained on all {len(rows)} rows) to {model_path}")

    metrics_path = model_path.with_suffix(".metrics.json")
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, default=float)
    print(f"Saved metrics to {metrics_path}")


if __name__ == "__main__":
    main()
