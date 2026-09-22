"""Trains roadmap module 13 - Admission Conversion Predictor.

Label: status == 'Enrolled' vs everything else (confirmed with John,
2026-09-22 - see ml/features.py POSITIVE_STATUS). Reads all dev leads via
DEV_DATABASE_URL (same connection pattern as the repo's check_*.py audit
scripts), trains a Logistic Regression pipeline (class_weight='balanced' -
positive rate is ~18%, chosen over XGBoost for this dataset size: 507 rows
is small enough that XGBoost's extra variance isn't worth it yet), evaluates
on a held-out stratified split, and saves the fitted pipeline to
settings.CONVERSION_MODEL_PATH (never hardcoded - see app/core/config.py).

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
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split

from app.core.config import settings
from ml.features import TRAINING_SELECT_COLUMNS, make_label, rows_to_frame
from ml.pipeline import RANDOM_STATE, build_pipeline


def load_dev_leads() -> list[dict]:
    """ORDER BY id: without an explicit order, Postgres can return rows in a
    different physical order between runs even when nothing changed, which
    silently shifts which rows train_test_split's fixed RANDOM_STATE puts in
    train vs. test - making metrics non-reproducible run to run for reasons
    that have nothing to do with the model. Ordering by id fixes that."""
    conn = psycopg2.connect(settings.DEV_DATABASE_URL)
    conn.set_session(readonly=True, autocommit=True)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cols = ", ".join(TRAINING_SELECT_COLUMNS)
    cur.execute(f"SELECT {cols} FROM public.leads ORDER BY id;")
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

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=RANDOM_STATE
    )

    pipeline = build_pipeline()
    pipeline.fit(X_train, y_train)

    y_pred = pipeline.predict(X_test)
    y_proba = pipeline.predict_proba(X_test)[:, 1]

    metrics = {
        "n_train": len(X_train),
        "n_test": len(X_test),
        "accuracy": accuracy_score(y_test, y_pred),
        "precision": precision_score(y_test, y_pred, zero_division=0),
        "recall": recall_score(y_test, y_pred, zero_division=0),
        "f1": f1_score(y_test, y_pred, zero_division=0),
        "roc_auc": roc_auc_score(y_test, y_proba),
        "confusion_matrix": confusion_matrix(y_test, y_pred).tolist(),
    }

    print("\n-- Test set metrics --")
    for k, v in metrics.items():
        print(f"{k}: {v}")
    print("\n-- Full classification report --")
    print(classification_report(y_test, y_pred, target_names=["Not Enrolled", "Enrolled"], zero_division=0))

    model_path = Path(__file__).resolve().parent.parent / settings.CONVERSION_MODEL_PATH
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, model_path)
    print(f"\nSaved model to {model_path}")

    metrics_path = model_path.with_suffix(".metrics.json")
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, default=float)
    print(f"Saved metrics to {metrics_path}")


if __name__ == "__main__":
    main()
