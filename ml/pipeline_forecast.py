"""Regression pipeline for roadmap module 20 (Time Series Demand
Forecaster) - a third, genuinely different pipeline shape alongside
ml/pipeline.py (tabular classification) and ml/pipeline_text.py (text
classification). This one predicts a continuous monthly enquiry count, not
a class probability, so it has no OneHotEncoder step (this module has no
categorical features - see ml/features_demand_forecast.py) and uses
RidgeCV instead of LogisticRegressionCV."""
import numpy as np
from sklearn.linear_model import RidgeCV
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


def build_forecast_pipeline() -> Pipeline:
    # RidgeCV auto-tunes its regularization strength via internal
    # leave-one-out CV on the training fold only (never touches the
    # held-out test fold) - same reasoning as LogisticRegressionCV in
    # ml/pipeline.py, appropriate here given only ~40-50 training rows.
    alphas = np.logspace(-3, 3, 25)
    return Pipeline(steps=[
        ("scale", StandardScaler()),
        ("regress", RidgeCV(alphas=alphas)),
    ])
