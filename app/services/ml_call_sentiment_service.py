import logging
from functools import lru_cache
from pathlib import Path

from app.core.config import settings
from ml.features_call_sentiment import notes_to_text

logger = logging.getLogger(__name__)

# app/services/ml_call_sentiment_service.py -> app/services -> app -> repo root
REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class ModelNotAvailableError(RuntimeError):
    """Raised when the trained artifact hasn't been produced yet (run
    ml/train_call_sentiment_model.py) or fails to load. The router turns
    this into a 503, never a raw 500. Same pattern as every other ML
    service module here."""


@lru_cache
def get_call_sentiment_model():
    """Cached load of the fitted pipeline - one load per process, not per
    request (same lru_cache pattern as every other ML service module)."""
    import joblib

    model_path = REPO_ROOT / settings.CALL_SENTIMENT_MODEL_PATH
    if not model_path.exists():
        raise ModelNotAvailableError(
            f"No trained model at {model_path} - run ml/train_call_sentiment_model.py first."
        )
    try:
        return joblib.load(model_path)
    except Exception as e:
        logger.error("Failed to load call-sentiment model from %s: %s", model_path, e)
        raise ModelNotAvailableError(f"Model at {model_path} failed to load: {e}") from e


def predict_call_sentiment(notes: str) -> tuple[str, list[tuple[str, float]]]:
    """notes: the raw followups.notes text. Returns (predicted_label,
    [(label, probability), ...]) for all 3 classes. Uses
    named_steps["classify"].classes_ (not a bare model.classes_) to be
    explicit about which pipeline step the class order comes from."""
    model = get_call_sentiment_model()
    text = notes_to_text([{"notes": notes}])
    probabilities = model.predict_proba(text)[0]
    classes = model.named_steps["classify"].classes_
    scores = [(str(label), float(p)) for label, p in zip(classes, probabilities)]
    predicted_label = max(scores, key=lambda pair: pair[1])[0]
    return predicted_label, scores
