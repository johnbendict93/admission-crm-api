import logging
from functools import lru_cache
from pathlib import Path

import joblib
import pandas as pd

from app.core.config import settings
from ml.features_followup_timing import CANDIDATE_HOURS, frame_for_lead

logger = logging.getLogger(__name__)

# app/services/ml_followup_timing_service.py -> app/services -> app -> repo root
REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class ModelNotAvailableError(RuntimeError):
    """Raised when the trained artifact hasn't been produced yet (run
    ml/train_followup_timing_model.py) or fails to load. The router turns
    this into a 503, never a raw 500. Same pattern as
    ml_conversion_service.ModelNotAvailableError."""


@lru_cache
def get_followup_timing_model():
    """Cached load of the fitted pipeline - one load per process, not per
    request (same lru_cache pattern as get_conversion_model)."""
    model_path = REPO_ROOT / settings.FOLLOWUP_TIMING_MODEL_PATH
    if not model_path.exists():
        raise ModelNotAvailableError(
            f"No trained model at {model_path} - run ml/train_followup_timing_model.py first."
        )
    try:
        return joblib.load(model_path)
    except Exception as e:
        logger.error("Failed to load followup-timing model from %s: %s", model_path, e)
        raise ModelNotAvailableError(f"Model at {model_path} failed to load: {e}") from e


def predict_best_followup_time(lead: dict) -> tuple[int, float, list[tuple[int, float]]]:
    """Scores every candidate hour (9am-8pm, CANDIDATE_HOURS) for THIS lead -
    its assigned telecaller and its parent's occupation (Nov 2026: the hour
    x occupation pattern is what makes the answer differ per lead) - and
    ranks them. Missing values fall back to "Unknown", same as training.
    One small batch predict_proba call, not one call per hour."""
    model = get_followup_timing_model()
    probabilities = model.predict_proba(frame_for_lead(lead))[:, 1]
    ranked = sorted(zip(CANDIDATE_HOURS, probabilities), key=lambda pair: -pair[1])
    best_hour, best_probability = ranked[0]
    return int(best_hour), float(best_probability), [(int(h), float(p)) for h, p in ranked]
