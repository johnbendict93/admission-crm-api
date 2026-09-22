"""The model pipeline shared between training and label-definition
comparison (ml/train_conversion_model.py, ml/compare_label_definitions.py).
Kept separate from both so there's exactly one place that defines what the
model actually is."""
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegressionCV
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from ml.features import CATEGORICAL_FEATURES, NUMERIC_FEATURES

# Fixed so reruns/comparisons are apples-to-apples - a training convention,
# not a config value (Golden Rule's "no hardcoding" is about table names/
# URLs/secrets, not this).
RANDOM_STATE = 42


def build_pipeline() -> Pipeline:
    numeric_transformer = Pipeline(steps=[
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
    ])
    preprocessor = ColumnTransformer(transformers=[
        ("numeric", numeric_transformer, NUMERIC_FEATURES),
        ("categorical", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_FEATURES),
    ])
    # LogisticRegressionCV instead of a fixed-strength LogisticRegression:
    # regenerating the fake-lead data for modules 14/16/17 (Sept 2026) added
    # a real telecaller-skill effect into assigned_to - a categorical
    # feature this pipeline already used, but with only ~100-135 leads per
    # telecaller and a class_weight="balanced" objective, a fixed C=1.0 fit
    # started overfitting the small per-category counts (test ROC-AUC fell
    # to ~0.48-0.58 across reruns, down from 0.615 before). LogisticRegressionCV
    # picks the regularization strength itself via 5-fold CV on the training
    # fold only (never touches the held-out test set), which recovered
    # ROC-AUC to ~0.59-0.61 on local reruns of the new data - comparable to
    # the original model, not the artificially inflated number a hand-tuned
    # C could give.
    classifier = LogisticRegressionCV(class_weight="balanced", max_iter=2000, random_state=RANDOM_STATE,
                                       cv=5, Cs=15, scoring="roc_auc")
    return Pipeline(steps=[("preprocess", preprocessor), ("classify", classifier)])
