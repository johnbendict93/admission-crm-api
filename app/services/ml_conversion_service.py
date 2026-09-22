import logging
from functools import lru_cache
from pathlib import Path

import joblib

from app.core.config import settings
from ml.features import rows_to_frame

logger = logging.getLogger(__name__)

# app/services/ml_conversion_service.py -> app/services -> app -> repo root
REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class ModelNotAvailableError(RuntimeError):
    """Raised when the trained artifact hasn't been produced yet (run
    ml/train_conversion_model.py) or fails to load. The router turns this
    into a 503, never a raw 500."""


@lru_cache
def get_conversion_model():
    """Cached load of the fitted pipeline - same lru_cache pattern as
    get_supabase_client (app/core/database.py): one load per process, not
    per request."""
    model_path = REPO_ROOT / settings.CONVERSION_MODEL_PATH
    if not model_path.exists():
        raise ModelNotAvailableError(
            f"No trained model at {model_path} - run ml/train_conversion_model.py first."
        )
    try:
        return joblib.load(model_path)
    except Exception as e:
        logger.error("Failed to load conversion model from %s: %s", model_path, e)
        raise ModelNotAvailableError(f"Model at {model_path} failed to load: {e}") from e


def predict_conversion(lead: dict) -> tuple[float, str]:
    """lead: a raw lead dict as returned by leads_service.get_lead_by_id -
    rows_to_frame (ml/features.py) picks out exactly the columns the model
    was trained on, so extra keys like name/phone/status are ignored, not
    fed to the model."""
    model = get_conversion_model()
    frame = rows_to_frame([lead])
    probability = float(model.predict_proba(frame)[0, 1])
    label = "Likely to enroll" if probability >= 0.5 else "Unlikely to enroll"
    return probability, label
