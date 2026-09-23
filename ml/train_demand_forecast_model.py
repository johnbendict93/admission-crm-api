"""Trains roadmap module 20 - Time Series Demand Forecaster.

Predicts the number of enquiries (leads) expected in a given calendar
month. Training data is the seeded synthetic monthly history
(enquiry_monthly_history, scripts/seed_dev_enquiry_monthly_history.py)
COMBINED with the real monthly enquiry counts derived live from the leads
table itself (grouped by calendar month of created_at) - real data always
wins where the two overlap. See combine_history() below for exactly how.

Trains ml/pipeline_forecast.py's RidgeCV regression pipeline, evaluates
with TimeSeriesSplit (NOT the shuffled StratifiedKFold every classification
module here uses - see the comment above the CV call for why that would be
wrong for a forecaster), and saves the fitted pipeline to
settings.DEMAND_FORECAST_MODEL_PATH.

Run this yourself (needs your conda env / network - dev Supabase isn't
reachable from the cloud sandbox or the local Cowork shell):
    conda activate admission-crm-api
    python ml/train_demand_forecast_model.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import joblib
import psycopg2
import psycopg2.extras
from sklearn.model_selection import TimeSeriesSplit, cross_validate

from app.core.config import settings
from ml.features_demand_forecast import rows_to_frame
from ml.pipeline_forecast import build_forecast_pipeline

CV_SPLITS = 5
CV_SCORING = ["neg_mean_absolute_error", "neg_mean_absolute_percentage_error"]

SYNTHETIC_HISTORY_QUERY = """
    SELECT year, month, enquiry_count
    FROM public.enquiry_monthly_history
    WHERE deleted_at IS NULL
    ORDER BY year, month;
"""

# Real current enquiry volume, straight from leads - grouped by calendar
# month of created_at. Not filtered to "this year": whatever months the
# live leads table actually covers is exactly what should override the
# illustrative synthetic history for those months (see combine_history()).
REAL_MONTHLY_QUERY = """
    SELECT EXTRACT(YEAR FROM created_at)::int AS year,
           EXTRACT(MONTH FROM created_at)::int AS month,
           COUNT(*)::int AS enquiry_count
    FROM public.leads
    WHERE deleted_at IS NULL
    GROUP BY 1, 2
    ORDER BY 1, 2;
"""


def load_rows(query: str) -> list[dict]:
    conn = psycopg2.connect(settings.DEV_DATABASE_URL)
    conn.set_session(readonly=True, autocommit=True)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(query)
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()
    return rows


def combine_history(synthetic_rows: list[dict], real_rows: list[dict]) -> list[dict]:
    """One row per (year, month), sorted chronologically. Real leads data
    always wins over the seeded synthetic history for a month both cover -
    this matters at the boundary: real leads span whatever trailing window
    was last seeded (scripts/seed_dev_fake_leads.py's rolling 365-day
    window), which can overlap the synthetic years
    (scripts/seed_dev_enquiry_monthly_history.py's 2023-2025). Synthetic
    rows fill in every month real data doesn't reach."""
    combined = {(r["year"], r["month"]): r["enquiry_count"] for r in synthetic_rows}
    for r in real_rows:
        combined[(r["year"], r["month"])] = r["enquiry_count"]
    return [{"year": y, "month": m, "enquiry_count": c} for (y, m), c in sorted(combined.items())]


def main() -> None:
    if not settings.DEV_DATABASE_URL:
        print("DEV_DATABASE_URL not set - aborting.")
        sys.exit(1)

    synthetic_rows = load_rows(SYNTHETIC_HISTORY_QUERY)
    real_rows = load_rows(REAL_MONTHLY_QUERY)
    print(f"Loaded {len(synthetic_rows)} synthetic history rows and {len(real_rows)} real monthly-leads rows from dev.")
    if not synthetic_rows:
        sys.exit("REFUSING: no rows in enquiry_monthly_history - run scripts/seed_dev_enquiry_monthly_history.py --apply first.")

    rows = combine_history(synthetic_rows, real_rows)
    print(f"Combined into {len(rows)} unique (year, month) rows, {rows[0]['year']}-{rows[0]['month']:02d} "
          f"through {rows[-1]['year']}-{rows[-1]['month']:02d}.")

    if len(rows) < CV_SPLITS + 1:
        sys.exit(f"REFUSING: only {len(rows)} monthly rows - need at least {CV_SPLITS + 1} for {CV_SPLITS}-fold TimeSeriesSplit CV.")

    X = rows_to_frame(rows)
    y = [r["enquiry_count"] for r in rows]

    # TimeSeriesSplit, not the shuffled StratifiedKFold every classification
    # module here uses: rows are already sorted chronologically
    # (combine_history's sorted()). Shuffling them the way a normal K-fold
    # would let the model "see the future" (train on a later month, test on
    # an earlier one), which silently inflates a forecaster's CV score.
    # Each TimeSeriesSplit fold trains on a growing earlier block and tests
    # on the months right after it - closer to how this model is actually
    # used at prediction time: forecasting a month it has never seen, using
    # only months before it.
    tscv = TimeSeriesSplit(n_splits=CV_SPLITS)
    cv = cross_validate(build_forecast_pipeline(), X, y, cv=tscv, scoring=CV_SCORING)

    metrics = {
        "n_rows": len(rows),
        "n_synthetic_rows": len(synthetic_rows),
        "n_real_rows": len(real_rows),
        "cv_folds": CV_SPLITS,
        "date_range": f"{rows[0]['year']}-{rows[0]['month']:02d} to {rows[-1]['year']}-{rows[-1]['month']:02d}",
    }
    print(f"\n-- {CV_SPLITS}-fold time-series cross-validated metrics (each fold tests on months after its training block) --")
    for name in CV_SCORING:
        scores = cv[f"test_{name}"]
        # sklearn's "neg_*" scorers are negated so higher-is-better for
        # every scorer; flip back to a plain, readable MAE/MAPE here.
        pretty = name.replace("neg_", "")
        metrics[f"cv_{pretty}_mean"] = -scores.mean()
        metrics[f"cv_{pretty}_std"] = scores.std()
        metrics[f"cv_{pretty}_folds"] = (-scores).tolist()
        print(f"{pretty:28}: mean={-scores.mean():.3f}  std={scores.std():.3f}  folds={[round(-s, 3) for s in scores]}")

    # Final deployed model: fit on ALL available data, same reasoning as
    # every other module here - the CV above already gives the honest
    # generalization estimate.
    pipeline = build_forecast_pipeline()
    pipeline.fit(X, y)

    model_path = Path(__file__).resolve().parent.parent / settings.DEMAND_FORECAST_MODEL_PATH
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, model_path)
    print(f"\nSaved model (trained on all {len(rows)} monthly rows) to {model_path}")

    metrics_path = model_path.with_suffix(".metrics.json")
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2, default=float)
    print(f"Saved metrics to {metrics_path}")


if __name__ == "__main__":
    main()
