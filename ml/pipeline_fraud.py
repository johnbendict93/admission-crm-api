"""Unsupervised anomaly-detection pipeline for roadmap module 22 (Fraud
Anomaly Detection) - a fourth, genuinely different pipeline shape alongside
ml/pipeline.py (tabular classification), ml/pipeline_text.py (text
classification), and ml/pipeline_forecast.py (time-series regression).
IsolationForest, not a classifier or regressor: it needs no label at all,
scoring each row by how easy it is to isolate from the rest of the
population - exactly the "no confirmed fraud yet" situation a real fraud
detector has to work in."""
from sklearn.ensemble import IsolationForest
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

RANDOM_STATE = 42


def build_fraud_pipeline() -> Pipeline:
    # contamination="auto" (sklearn's own heuristic), NOT the actual known
    # planted-fraud rate: a real production deployment could never measure
    # that rate (no ground truth to measure it from), and using the known
    # rate here would quietly leak the evaluation labels into the model's
    # own hyperparameters - see ml/features_fraud_detection.py's module
    # docstring for why the ground truth stays eval-only everywhere else
    # in this module too.
    return Pipeline(steps=[
        ("scale", StandardScaler()),
        ("detect", IsolationForest(contamination="auto", random_state=RANDOM_STATE, n_estimators=200)),
    ])
