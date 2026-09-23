"""The model pipeline shared between every leads/followups-based ML module
(ml/train_conversion_model.py, ml/compare_label_definitions.py,
ml/train_followup_timing_model.py). Kept separate from all of them so
there's exactly one place that defines what the underlying model actually
is - build_pipeline() takes the feature lists as arguments (defaulting to
module 13's leads features for backward compatibility) so each module can
supply its own numeric/categorical columns without duplicating the
preprocessing + classifier setup."""
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


def build_pipeline(numeric_features: list[str] | None = None,
                    categorical_features: list[str] | None = None,
                    cv_scoring: str = "roc_auc") -> Pipeline:
    numeric_features = NUMERIC_FEATURES if numeric_features is None else numeric_features
    categorical_features = CATEGORICAL_FEATURES if categorical_features is None else categorical_features
    numeric_transformer = Pipeline(steps=[
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
    ])
    preprocessor = ColumnTransformer(transformers=[
        ("numeric", numeric_transformer, numeric_features),
        ("categorical", OneHotEncoder(handle_unknown="ignore"), categorical_features),
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
    #
    # cv_scoring (default "roc_auc", unchanged for modules 13/14/16/17):
    # found while building module 18 that ROC-AUC is scale-invariant - for
    # a model with a SINGLE categorical feature (no numeric features at
    # all, module 18's case), every candidate C in the grid produces
    # IDENTICAL internal CV ROC-AUC (the ranking of one-hot categories
    # doesn't change under any positive rescaling of the coefficients), so
    # LogisticRegressionCV degenerately picks the smallest/strongest C on
    # the grid - true ranking ability (a real, non-degenerate outer-loop
    # ROC-AUC) survives, but predict_proba collapses every prediction to
    # ~0.5, which is useless for an endpoint whose whole point is a
    # calibrated risk score. "neg_log_loss" (module 18 passes this
    # explicitly) DOES depend on how spread out the probabilities are, so
    # it breaks that degeneracy and picks a C that actually differentiates
    # categories. Modules with at least one numeric feature never hit this
    # (numeric features already vary continuously, so C-scale is never
    # degenerate for them) - confirmed by leaving their default unchanged.
    classifier = LogisticRegressionCV(class_weight="balanced", max_iter=2000, random_state=RANDOM_STATE,
                                       cv=5, Cs=15, scoring=cv_scoring)
    return Pipeline(steps=[("preprocess", preprocessor), ("classify", classifier)])
