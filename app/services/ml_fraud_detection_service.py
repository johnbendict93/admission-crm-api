import logging
from functools import lru_cache
from pathlib import Path

from postgrest.exceptions import APIError
from supabase import Client

from app.core.config import settings
from ml.features_fraud_detection import rows_to_frame

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class ModelNotAvailableError(RuntimeError):
    """Raised when the trained artifact hasn't been produced yet (run
    ml/train_fraud_detection_model.py) or fails to load. The router turns
    this into a 503, never a raw 500. Same pattern as every other ML
    module's ModelNotAvailableError."""


@lru_cache
def get_fraud_detection_model():
    """Cached load of the fitted pipeline - one load per process, not per
    request (same lru_cache pattern as every other ml_*_service loader)."""
    import joblib

    model_path = REPO_ROOT / settings.FRAUD_DETECTION_MODEL_PATH
    if not model_path.exists():
        raise ModelNotAvailableError(
            f"No trained model at {model_path} - run ml/train_fraud_detection_model.py first."
        )
    try:
        return joblib.load(model_path)
    except Exception as e:
        logger.error("Failed to load fraud-detection model from %s: %s", model_path, e)
        raise ModelNotAvailableError(f"Model at {model_path} failed to load: {e}") from e


def _count_other_leads(supabase: Client, column: str, value, exclude_id: str) -> int:
    """How many OTHER leads (not this one) share this exact value in
    `column` - the live, single-lead equivalent of the training query's
    COUNT(*) OVER (PARTITION BY ...) - 1. Two live count queries per
    prediction (phone, then created_at) - fine for a single-lead,
    on-demand endpoint, not a bulk job."""
    try:
        response = (
            supabase.table(settings.LEADS_TABLE)
            .select("id", count="exact")
            .eq(column, value)
            .neq("id", exclude_id)
            .is_("deleted_at", "null")
            .execute()
        )
    except APIError as e:
        logger.error("Supabase error counting %s duplicates: %s", column, e)
        raise
    return response.count or 0


def predict_fraud_score(supabase: Client, lead: dict) -> tuple[float, bool]:
    """lead: the raw lead dict (leads_service.get_lead_by_id). Returns
    (anomaly_score, is_anomalous) - see app/models/ml_fraud_detection.py
    for what these mean."""
    model = get_fraud_detection_model()
    phone_dup = _count_other_leads(supabase, "phone", lead["phone"], lead["id"]) if lead.get("phone") else 0
    ts_dup = _count_other_leads(supabase, "created_at", lead["created_at"], lead["id"]) if lead.get("created_at") else 0
    row = {**lead, "phone_duplicate_count": phone_dup, "timestamp_duplicate_count": ts_dup}
    frame = rows_to_frame([row])
    score = float(model.decision_function(frame)[0])
    is_anomalous = bool(model.predict(frame)[0] == -1)
    return score, is_anomalous
