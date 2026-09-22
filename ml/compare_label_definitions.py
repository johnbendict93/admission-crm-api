"""Diagnostic, not part of the shipped pipeline: settles which module-13
label definition is actually better using 5-fold cross-validation instead
of a single train/test split.

Why this exists: a single 80/20 split on ~80-100 test rows with ~18-20
positives has huge variance - one split showed AUC 0.615 for "Enrolled vs
everything else", the very next (different label, different split) showed
0.522 for "Enrolled vs Lost only". That swing is consistent with sampling
noise, not necessarily a real difference between the two label choices.
Cross-validation (mean +/- std across 5 folds) is the correct way to tell
signal from split luck here.

Run this yourself (needs your conda env / network):
    conda activate admission-crm-api
    python ml/compare_label_definitions.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import psycopg2
import psycopg2.extras
from sklearn.model_selection import StratifiedKFold, cross_validate

from app.core.config import settings
from ml.features import TRAINING_SELECT_COLUMNS, filter_resolved, make_label, rows_to_frame
from ml.pipeline import RANDOM_STATE, build_pipeline

N_FOLDS = 5
SCORING = ["roc_auc", "f1", "precision", "recall"]


def load_dev_leads() -> list[dict]:
    conn = psycopg2.connect(settings.DEV_DATABASE_URL)
    conn.set_session(readonly=True, autocommit=True)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cols = ", ".join(TRAINING_SELECT_COLUMNS)
    cur.execute(f"SELECT {cols} FROM public.leads;")
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()
    return rows


def evaluate(label: str, rows: list[dict]) -> None:
    X = rows_to_frame(rows)
    y = [make_label(r["status"]) for r in rows]
    n_pos, n = sum(y), len(y)
    print(f"\n-- {label} -- n={n}, positives={n_pos} ({n_pos / n:.1%})")

    cv = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=RANDOM_STATE)
    results = cross_validate(build_pipeline(), X, y, cv=cv, scoring=SCORING)

    for metric in SCORING:
        scores = results[f"test_{metric}"]
        print(f"{metric:10s}: mean={scores.mean():.3f}  std={scores.std():.3f}  folds={np.round(scores, 3).tolist()}")


def main() -> None:
    if not settings.DEV_DATABASE_URL:
        print("DEV_DATABASE_URL not set - aborting.")
        sys.exit(1)

    rows = load_dev_leads()
    print(f"Loaded {len(rows)} leads from dev.")

    evaluate("Enrolled vs everything else (all leads)", rows)
    evaluate("Enrolled vs Lost only (resolved leads)", filter_resolved(rows))


if __name__ == "__main__":
    main()
