"""Trains roadmap module 19 - NLP Call Sentiment Analyzer.

Label: derived from followups.response, a short fixed categorical phrase
(see ml/features_call_sentiment.py's make_label) - not a separate stored
column. Feature: followups.notes (free text) via TF-IDF (ml/pipeline_text.py).
Reads dev followups directly via DEV_DATABASE_URL (same connection pattern
as every other train_*.py script here) - no join needed, response/notes
both live on followups itself. Evaluates with 5-fold stratified CV using
accuracy + macro-averaged precision/recall/F1 (not ROC-AUC, which needs
one-vs-rest handling for a 3-class problem and isn't the natural metric
for a sentiment classifier anyway), and saves the fitted pipeline to
settings.CALL_SENTIMENT_MODEL_PATH.

IMPORTANT: run scripts/enrich_dev_followup_notes.py --apply BEFORE this,
at least once - without it, dev's existing followups still carry the old
3-template notes text (pre module-19), which this script would happily
train on but with far less lexical variety than the new bank provides.

Run this yourself (needs your conda env / network - dev Supabase isn't
reachable from the cloud sandbox or the local Cowork shell):
    conda activate admission-crm-api
    python ml/train_call_sentiment_model.py
"""
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import joblib
import psycopg2
import psycopg2.extras
from sklearn.model_selection import StratifiedKFold, cross_validate

from app.core.config import settings
from ml.features_call_sentiment import make_label, notes_to_text
from ml.pipeline_text import RANDOM_STATE, build_text_pipeline

CV_FOLDS = 5
CV_SCORING = ["accuracy", "f1_macro", "precision_macro", "recall_macro"]

TRAINING_QUERY = """
    SELECT response, notes
    FROM public.followups
    WHERE deleted_at IS NULL
    ORDER BY id;
"""


def load_dev_followups() -> list[dict]:
    """ORDER BY id for the same reproducibility reason as every other
    train_*.py script here."""
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

    rows = load_dev_followups()
    print(f"Loaded {len(rows)} followups from dev.")

    labeled_rows = [r for r in rows if make_label(r["response"]) is not None]
    skipped = len(rows) - len(labeled_rows)
    if skipped:
        print(f"Skipping {skipped} followups whose response isn't one of the known fixed phrases.")

    X = notes_to_text(labeled_rows)
    y = [make_label(r["response"]) for r in labeled_rows]
    counts = Counter(y)
    print(f"Label balance: {dict(counts)}")
    if min(counts.values()) < CV_FOLDS:
        sys.exit(f"REFUSING: smallest class has only {min(counts.values())} rows, need >= {CV_FOLDS} for "
                  f"{CV_FOLDS}-fold stratified CV. Seed/enrich more followups first.")

    skf = StratifiedKFold(n_splits=CV_FOLDS, shuffle=True, random_state=RANDOM_STATE)
    cv = cross_validate(build_text_pipeline(), X, y, cv=skf, scoring=CV_SCORING)

    metrics = {"n_rows": len(labeled_rows), "n_skipped": skipped, "cv_folds": CV_FOLDS, "label_counts": dict(counts)}
    print(f"\n-- {CV_FOLDS}-fold cross-validated metrics (each row used as test exactly once) --")
    for name in CV_SCORING:
        scores = cv[f"test_{name}"]
        metrics[f"cv_{name}_mean"] = scores.mean()
        metrics[f"cv_{name}_std"] = scores.std()
        metrics[f"cv_{name}_folds"] = scores.tolist()
        print(f"{name:16}: mean={scores.mean():.3f}  std={scores.std():.3f}  folds={[round(s, 3) for s in scores]}")

    # Final deployed model: fit on ALL available data, same reasoning as
    # every other module here - CV above already gives the honest
    # generalization estimate.
    pipeline = build_text_pipeline()
    pipeline.fit(X, y)

    model_path = Path(__file__).resolve().parent.parent / settings.CALL_SENTIMENT_MODEL_PATH
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, model_path)
    print(f"\nSaved model (trained on all {len(labeled_rows)} rows) to {model_path}")

    metrics_path = model_path.with_suffix(".metrics.json")
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, default=float)
    print(f"Saved metrics to {metrics_path}")


if __name__ == "__main__":
    main()
