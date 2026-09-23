"""Feature definitions for roadmap module 20 - Time Series Demand
Forecaster. Predicts the number of enquiries (leads) expected in a given
calendar month, from the month itself - no other input. This is
deliberately a PURE function of (year, month): nothing here reads the
database, unlike every classification module in this repo, which is what
lets app/services/ml_demand_forecast_service.py forecast any future month,
not just ones present in the training data.

FEATURES:
  * time_index - (year - BASE_YEAR) * 12 + (month - 1). A simple integer
    trend variable: 0 for the first historical month (BASE_YEAR-01),
    counting up by 1 each month after that. Captures long-run growth.
    BASE_YEAR is tied to scripts/seed_dev_enquiry_monthly_history.py's
    earliest synthetic year (2023) - if that script's ANNUAL_TOTALS ever
    changes to start somewhere else, update BASE_YEAR here too and retrain.
  * month_sin / month_cos - a cyclical (sin/cos) encoding of the calendar
    month, not a raw 1-12 integer or a one-hot per month. A raw integer
    would tell the model December (12) is "far" from January (1), which is
    backwards - they're adjacent months. A one-hot would need a separate
    coefficient per month, which ~40-50 training rows (2-4 years) can't
    support well (same small-table lesson as module 18's fee default
    risk). Sin/cos gives the model a smooth, 2-number seasonal signal
    instead.

No categorical features, so this module's pipeline
(ml/pipeline_forecast.py) has no OneHotEncoder step at all - a third
pipeline shape alongside ml/pipeline.py (tabular classification) and
ml/pipeline_text.py (text classification)."""
import math

import pandas as pd

BASE_YEAR = 2023  # keep in sync with scripts/seed_dev_enquiry_monthly_history.py's earliest ANNUAL_TOTALS year

NUMERIC_FEATURES = ["time_index", "month_sin", "month_cos"]
FEATURE_COLUMNS = NUMERIC_FEATURES  # no categorical features in this module


def time_index(year: int, month: int) -> int:
    return (year - BASE_YEAR) * 12 + (month - 1)


def month_sin(month: int) -> float:
    return math.sin(2 * math.pi * month / 12)


def month_cos(month: int) -> float:
    return math.cos(2 * math.pi * month / 12)


def rows_to_frame(rows: list[dict]) -> pd.DataFrame:
    """Raw rows (list of dicts with at least "year" and "month") -> a
    DataFrame with exactly FEATURE_COLUMNS, in order. Works identically
    whether the row is historical (from combine_history() in the training
    script) or a bare {"year": ..., "month": ...} forecast request (the
    live service) - the features are a pure function of the calendar date
    either way."""
    records = [
        {
            "time_index": time_index(r["year"], r["month"]),
            "month_sin": month_sin(r["month"]),
            "month_cos": month_cos(r["month"]),
        }
        for r in rows
    ]
    return pd.DataFrame.from_records(records, columns=FEATURE_COLUMNS)
