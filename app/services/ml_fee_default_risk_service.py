import logging
from functools import lru_cache
from pathlib import Path

from app.core.config import settings
from ml.features_fee_default_risk import rows_to_frame

logger = logging.getLogger(__name__)

# app/services/ml_fee_default_risk_service.py -> app/services -> app -> repo root
REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class ModelNotAvailableError(RuntimeError):
    """Raised when the trained artifact hasn't been produced yet (run
    ml/train_fee_default_risk_model.py) or fails to load. The router turns
    this into a 503, never a raw 500. Same pattern as
    ml_dropout_risk_service.ModelNotAvailableError."""


@lru_cache
def get_fee_default_risk_model():
    """Cached load of the fitted pipeline - one load per process, not per
    request (same lru_cache pattern as get_dropout_risk_model)."""
    import joblib

    model_path = REPO_ROOT / settings.FEE_DEFAULT_RISK_MODEL_PATH
    if not model_path.exists():
        raise ModelNotAvailableError(
            f"No trained model at {model_path} - run ml/train_fee_default_risk_model.py first."
        )
    try:
        return joblib.load(model_path)
    except Exception as e:
        logger.error("Failed to load fee-default-risk model from %s: %s", model_path, e)
        raise ModelNotAvailableError(f"Model at {model_path} failed to load: {e}") from e


def predict_fee_default_risk(applicant: dict) -> tuple[float, str]:
    """applicant: the linked applicant dict (applicants_service.
    get_applicant_by_id(fee_due_schedule_row['applicant_id'])) -
    rows_to_frame picks out exactly the column (parent_occupation) the
    model was trained on. The fee_due_schedule row itself (amount_due,
    due_date, fee_component) carries no model feature - see
    ml/features_fee_default_risk.py's docstring for why - it's only used
    by the router to build the response."""
    model = get_fee_default_risk_model()
    row = {"parent_occupation": applicant.get("parent_occupation")}
    frame = rows_to_frame([row])
    probability = float(model.predict_proba(frame)[0, 1])
    label = "At risk of default" if probability >= 0.5 else "Likely to pay"
    return probability, label
