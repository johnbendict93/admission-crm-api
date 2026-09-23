import logging
from functools import lru_cache
from pathlib import Path

from app.core.config import settings
from ml.features_demand_forecast import rows_to_frame

logger = logging.getLogger(__name__)

# app/services/ml_demand_forecast_service.py -> app/services -> app -> repo root
REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class ModelNotAvailableError(RuntimeError):
    """Raised when the trained artifact hasn't been produced yet (run
    ml/train_demand_forecast_model.py) or fails to load. The router turns
    this into a 503, never a raw 500. Same pattern as every other ML
    module's ModelNotAvailableError."""


@lru_cache
def get_demand_forecast_model():
    """Cached load of the fitted pipeline - one load per process, not per
    request (same lru_cache pattern as every other ml_*_service loader)."""
    import joblib

    model_path = REPO_ROOT / settings.DEMAND_FORECAST_MODEL_PATH
    if not model_path.exists():
        raise ModelNotAvailableError(
            f"No trained model at {model_path} - run ml/train_demand_forecast_model.py first."
        )
    try:
        return joblib.load(model_path)
    except Exception as e:
        logger.error("Failed to load demand-forecast model from %s: %s", model_path, e)
        raise ModelNotAvailableError(f"Model at {model_path} failed to load: {e}") from e


def predict_demand(year: int, month: int) -> float:
    """Predicts the enquiry count for a given (year, month). A pure
    function of the calendar date - see ml/features_demand_forecast.py for
    how time_index/month_sin/month_cos are derived - so this works for any
    future month, not just ones seen during training: a genuine forecast,
    not a lookup. Clipped at 0: a linear model can predict a negative count
    for a quiet-enough month, which is never a real answer."""
    model = get_demand_forecast_model()
    frame = rows_to_frame([{"year": year, "month": month}])
    prediction = float(model.predict(frame)[0])
    return max(0.0, prediction)
