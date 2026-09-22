from fastapi import APIRouter, Depends, HTTPException
from postgrest.exceptions import APIError
from supabase import Client

from app.core.config import settings
from app.core.database import get_supabase_client
from app.core.jwt_auth import get_current_user
from app.models.ml_conversion import ConversionPredictionResponse
from app.services import leads_service
from app.services.ml_conversion_service import ModelNotAvailableError, predict_conversion

router = APIRouter(prefix="/ml", tags=["ML - Conversion Prediction"])


@router.get("/leads/{lead_id}/conversion-prediction", response_model=ConversionPredictionResponse)
def get_conversion_prediction(
    lead_id: str,
    supabase: Client = Depends(get_supabase_client),
    current_user: dict = Depends(get_current_user),
):
    """Predicts this lead's probability of eventually enrolling (roadmap
    module 13 - see ml/train_conversion_model.py for the model itself).
    Read-only: never writes anything back to the lead."""
    try:
        lead = leads_service.get_lead_by_id(supabase, lead_id)
    except APIError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {e.message}")
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    try:
        probability, label = predict_conversion(lead)
    except ModelNotAvailableError as e:
        raise HTTPException(status_code=503, detail=str(e))

    return ConversionPredictionResponse(
        lead_id=lead_id,
        probability=round(probability, 4),
        predicted_label=label,
        model_version=settings.CONVERSION_MODEL_PATH,
    )
