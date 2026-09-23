import logging
from functools import lru_cache
from pathlib import Path

from app.core.config import settings
from ml.features_dropout_risk import rows_to_frame

logger = logging.getLogger(__name__)

# app/services/ml_dropout_risk_service.py -> app/services -> app -> repo root
REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class ModelNotAvailableError(RuntimeError):
    """Raised when the trained artifact hasn't been produced yet (run
    ml/train_dropout_risk_model.py) or fails to load. The router turns
    this into a 503, never a raw 500. Same pattern as
    ml_conversion_service.ModelNotAvailableError."""


@lru_cache
def get_dropout_risk_model():
    """Cached load of the fitted pipeline - one load per process, not per
    request (same lru_cache pattern as get_conversion_model)."""
    import joblib

    model_path = REPO_ROOT / settings.DROPOUT_RISK_MODEL_PATH
    if not model_path.exists():
        raise ModelNotAvailableError(
            f"No trained model at {model_path} - run ml/train_dropout_risk_model.py first."
        )
    try:
        return joblib.load(model_path)
    except Exception as e:
        logger.error("Failed to load dropout-risk model from %s: %s", model_path, e)
        raise ModelNotAvailableError(f"Model at {model_path} failed to load: {e}") from e


def predict_dropout_risk(application: dict, applicant: dict) -> tuple[float, str]:
    """application: a raw application dict (applications_service.
    get_application_by_id) - kept as a parameter for the endpoint to pass
    application_stage/id through for the response, even though the
    trimmed feature set (see ml/features_dropout_risk.py's docstring for
    why merit_rank/category/programme/department/lead_source were cut)
    no longer reads anything off it. applicant: the linked applicant dict
    (applicants_service.get_applicant_by_id(application['applicant_id']));
    rows_to_frame picks out exactly the columns the model was trained on."""
    model = get_dropout_risk_model()
    row = {
        "cutoff_marks": applicant.get("cutoff_marks"),
        "twelfth_percentage": applicant.get("twelfth_percentage"),
        "pcm_marks": applicant.get("pcm_marks"),
        "parent_occupation": applicant.get("parent_occupation"),
    }
    frame = rows_to_frame([row])
    probability = float(model.predict_proba(frame)[0, 1])
    label = "At risk of dropping out" if probability >= 0.5 else "Likely to complete"
    return probability, label
