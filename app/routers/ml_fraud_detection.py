from fastapi import APIRouter, Depends, HTTPException
from postgrest.exceptions import APIError
from supabase import Client

from app.core.config import settings
from app.core.database import get_supabase_client
from app.core.jwt_auth import get_current_user
from app.models.ml_fraud_detection import FraudScoreResponse
from app.services import leads_service
from app.services.ml_fraud_detection_service import ModelNotAvailableError, predict_fraud_score

router = APIRouter(prefix="/ml", tags=["ML - Fraud Detection"])


@router.get("/leads/{lead_id}/fraud-score", response_model=FraudScoreResponse)
def get_fraud_score(
    lead_id: str,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(get_current_user),
):
    """Scores how anomalous this lead looks compared to the rest of the
    leads table (roadmap module 22 - see ml/train_fraud_detection_model.py
    for the model itself). Unsupervised: there is no "confirmed fraud"
    label anywhere in this schema, by design - see
    ml/features_fraud_detection.py's docstring. Read-only; never writes
    anything back to the lead."""
    try:
        lead = leads_service.get_lead_by_id(supabase, lead_id)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    try:
        score, is_anomalous = predict_fraud_score(supabase, lead)
    except ModelNotAvailableError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")

    return FraudScoreResponse(
        lead_id=lead_id,
        anomaly_score=round(score, 4),
        is_anomalous=is_anomalous,
        model_version=settings.FRAUD_DETECTION_MODEL_PATH,
    )
