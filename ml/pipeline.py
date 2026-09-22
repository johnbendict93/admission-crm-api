"""The model pipeline shared between training and label-definition
comparison (ml/train_conversion_model.py, ml/compare_label_definitions.py).
Kept separate from both so there's exactly one place that defines what the
model actually is."""
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
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
    classifier = LogisticRegression(class_weight="balanced", max_iter=1000, random_state=RANDOM_STATE)
    return Pipeline(steps=[("preprocess", preprocessor), ("classify", classifier)])
