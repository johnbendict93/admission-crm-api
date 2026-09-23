"""Trains roadmap module 22 - Fraud Anomaly Detection.

Unsupervised: fits ml/pipeline_fraud.py's IsolationForest on every current
leads row (organic + the planted fraud rows from
scripts/seed_dev_fraud_leads.py - see that script's docstring for why the
fraud rows are INCLUDED here, unlike ml/train_conversion_model.py which
now explicitly EXCLUDES them). No label is used for fitting.

EVALUATION (not training): if scripts/seed_dev_fraud_leads.py's local
ground-truth file exists, this script ALSO reports how many of the
planted fraud leads the fitted model actually flagged as anomalous -
purely informational, computed after fitting, never fed back into the
model. This is the only place in this script the ground truth file is
read.

Run this yourself (needs your conda env / network - dev Supabase isn't
reachable from the cloud sandbox or the local Cowork shell):
    conda activate admission-crm-api
    python ml/train_fraud_detection_model.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import joblib
import psycopg2
import psycopg2.extras

from app.core.config import settings
from ml.features_fraud_detection import rows_to_frame
from ml.pipeline_fraud import build_fraud_pipeline

GROUND_TRUTH_PATH = Path(__file__).resolve().parent.parent / "ml" / "eval" / "fraud_ground_truth.json"

# Window functions compute phone_duplicate_count/timestamp_duplicate_count
# directly in SQL, against every OTHER row (COUNT(*) OVER (...) - 1, since
# the window includes the row itself) - one query, no per-row round trips.
# email is included here (unlike ml/features.py's TRAINING_SELECT_COLUMNS)
# purely to identify which rows are the planted fraud rows for the
# evaluation step below - it is never used as a model feature (see
# ml/features_fraud_detection.py's FEATURE_COLUMNS).
TRAINING_QUERY = """
    SELECT id, email, school, district, marks, score,
           COUNT(*) OVER (PARTITION BY phone) - 1 AS phone_duplicate_count,
           COUNT(*) OVER (PARTITION BY created_at) - 1 AS timestamp_duplicate_count
    FROM public.leads
    WHERE deleted_at IS NULL
    ORDER BY id;
"""


def load_dev_leads() -> list[dict]:
    conn = psycopg2.connect(settings.DEV_DATABASE_URL)
    conn.set_session(readonly=True, autocommit=True)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(TRAINING_QUERY)
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()
    return rows


def load_ground_truth() -> dict:
    if not GROUND_TRUTH_PATH.exists():
        return {}
    with open(GROUND_TRUTH_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    if not settings.DEV_DATABASE_URL:
        print("DEV_DATABASE_URL not set - aborting.")
        sys.exit(1)

    rows = load_dev_leads()
    print(f"Loaded {len(rows)} leads from dev (organic + any planted fraud rows).")
    if len(rows) < 20:
        sys.exit("REFUSING: too few leads to fit an anomaly detector meaningfully. Seed more leads first.")

    X = rows_to_frame(rows)
    pipeline = build_fraud_pipeline()
    pipeline.fit(X)

    # decision_function: higher = more normal, lower/negative = more
    # anomalous. Used only for reporting/evaluation below - predict() (the
    # -1/1 call used at inference time too) already used the same fitted
    # boundary internally.
    scores = pipeline.decision_function(X)
    predictions = pipeline.predict(X)  # -1 = anomaly, 1 = normal
    n_flagged = int((predictions == -1).sum())
    print(f"\nFlagged {n_flagged} / {len(rows)} leads as anomalous ({n_flagged / len(rows):.1%}).")

    ground_truth = load_ground_truth()
    metrics = {"n_rows": len(rows), "n_flagged": n_flagged}
    if ground_truth:
        id_to_flagged = {str(r["id"]): bool(p == -1) for r, p in zip(rows, predictions)}
        print(f"\n-- Evaluation against {len(ground_truth)} planted fraud leads (eval-only, not used for fitting) --")
        by_type: dict[str, list[bool]] = {}
        for lead_id, info in ground_truth.items():
            fraud_type = info["fraud_type"]
            if lead_id not in id_to_flagged:
                print(f"  WARNING: {lead_id} ({fraud_type}) not found in current leads - stale ground truth?")
                continue
            by_type.setdefault(fraud_type, []).append(id_to_flagged[lead_id])
        overall_caught = sum(sum(v) for v in by_type.values())
        overall_total = sum(len(v) for v in by_type.values())
        for fraud_type, results in sorted(by_type.items()):
            caught = sum(results)
            print(f"  {fraud_type:20}: caught {caught}/{len(results)}")
        if overall_total:
            print(f"  {'TOTAL':20}: caught {overall_caught}/{overall_total} ({overall_caught / overall_total:.1%})")
            metrics["ground_truth_recall"] = overall_caught / overall_total
        else:
            print("  no matching planted rows found in current leads")
            metrics["ground_truth_recall"] = None
        metrics["ground_truth_by_type"] = {k: f"{sum(v)}/{len(v)}" for k, v in by_type.items()}
    else:
        print("\nNo ground-truth file found (ml/eval/fraud_ground_truth.json) - skipping evaluation. "
              "Run scripts/seed_dev_fraud_leads.py --apply first to plant evaluable fraud leads.")

    model_path = Path(__file__).resolve().parent.parent / settings.FRAUD_DETECTION_MODEL_PATH
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, model_path)
    print(f"\nSaved model (trained on all {len(rows)} leads) to {model_path}")

    metrics_path = model_path.with_suffix(".metrics.json")
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, default=float)
    print(f"Saved metrics to {metrics_path}")


if __name__ == "__main__":
    main()
